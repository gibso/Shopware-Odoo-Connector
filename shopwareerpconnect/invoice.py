# -*- coding: utf-8 -*-
##############################################################################
#
#    Author: Joël Grand-Guillaume, Guewen Baconnier
#    Copyright 2013 Camptocamp SA
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging
import xmlrpclib
from openerp import models, fields, _
from openerp.addons.connector.queue.job import job, related_action
from openerp.addons.connector.unit.synchronizer import Exporter
from openerp.addons.connector.event import on_record_create
from openerp.addons.connector_ecommerce.event import (on_invoice_paid,
                                                      on_invoice_validated)
from openerp.addons.connector.exception import IDMissingInBackend
from .unit.backend_adapter import GenericAdapter
from .connector import get_environment
from .backend import shopware
from .related_action import unwrap_binding

_logger = logging.getLogger(__name__)


class ShopwareAccountInvoice(models.Model):
    """ Binding Model for the Shopware Invoice """
    _name = 'shopware.account.invoice'
    _inherit = 'shopware.binding'
    _inherits = {'account.invoice': 'openerp_id'}
    _description = 'Shopware Invoice'

    openerp_id = fields.Many2one(comodel_name='account.invoice',
                                 string='Invoice',
                                 required=True,
                                 ondelete='cascade')
    shopware_order_id = fields.Many2one(comodel_name='shopware.sale.order',
                                       string='Shopware Sale Order',
                                       ondelete='set null')

    _sql_constraints = [
        ('openerp_uniq', 'unique(backend_id, openerp_id)',
         'A Shopware binding for this invoice already exists.'),
    ]


class AccountInvoice(models.Model):
    """ Adds the ``one2many`` relation to the Shopware bindings
    (``shopware_bind_ids``)
    """
    _inherit = 'account.invoice'

    shopware_bind_ids = fields.One2many(
        comodel_name='shopware.account.invoice',
        inverse_name='openerp_id',
        string='Shopware Bindings',
    )


@shopware
class AccountInvoiceAdapter(GenericAdapter):
    """ Backend Adapter for the Shopware Invoice """
    _model_name = 'shopware.account.invoice'
    _shopware_model = 'sales_order_invoice'
    _admin_path = 'sales_invoice/view/invoice_id/{id}'

    def _call(self, method, arguments):
        try:
            return super(AccountInvoiceAdapter, self)._call(method, arguments)
        except xmlrpclib.Fault as err:
            # this is the error in the Shopware API
            # when the invoice does not exist
            if err.faultCode == 100:
                raise IDMissingInBackend
            else:
                raise

    def create(self, order_increment_id, items, comment, email,
               include_comment):
        """ Create a record on the external system """
        return self._call('%s.create' % self._shopware_model,
                          [order_increment_id, items, comment,
                           email, include_comment])

    def search_read(self, filters=None, order_id=None):
        """ Search records according to some criterias
        and returns their information

        :param order_id: 'order_id' field of the shopware sale order, this
                         is not the same field than 'increment_id'
        """
        if filters is None:
            filters = {}
        if order_id is not None:
            filters['order_id'] = {'eq': order_id}
        return super(AccountInvoiceAdapter, self).search_read(filters=filters)


@shopware
class ShopwareInvoiceExporter(Exporter):
    """ Export invoices to Shopware """
    _model_name = ['shopware.account.invoice']

    def _export_invoice(self, shopware_id, lines_info, mail_notification):
        if not lines_info:  # invoice without any line for the sale order
            return
        return self.backend_adapter.create(shopware_id,
                                           lines_info,
                                           _("Invoice Created"),
                                           mail_notification,
                                           False)

    def _get_lines_info(self, invoice):
        """
        Get the line to export to Shopware. In case some lines doesn't have a
        matching on Shopware, we ignore them. This allow to add lines manually.

        :param invoice: invoice is an shopware.account.invoice record
        :type invoice: browse_record
        :return: dict of {shopware_product_id: quantity}
        :rtype: dict
        """
        item_qty = {}
        # get product and quantities to invoice
        # if no shopware id found, do not export it
        order = invoice.shopware_order_id
        for line in invoice.invoice_line:
            product = line.product_id
            # find the order line with the same product
            # and get the shopware item_id (id of the line)
            # to invoice
            order_line = next((line for line in order.shopware_order_line_ids
                               if line.product_id.id == product.id),
                              None)
            if order_line is None:
                continue

            item_id = order_line.shopware_id
            item_qty.setdefault(item_id, 0)
            item_qty[item_id] += line.quantity
        return item_qty

    def run(self, binding_id):
        """ Run the job to export the validated/paid invoice """
        invoice = self.model.browse(binding_id)

        shopware_order = invoice.shopware_order_id
        shopware_shop = shopware_order.shop_id
        mail_notification = shopware_shop.send_invoice_paid_mail

        lines_info = self._get_lines_info(invoice)
        shopware_id = None
        try:
            shopware_id = self._export_invoice(shopware_order.shopware_id,
                                              lines_info,
                                              mail_notification)
        except xmlrpclib.Fault as err:
            # When the invoice is already created on Shopware, it returns:
            # <Fault 102: 'Cannot do invoice for order.'>
            # We'll search the Shopware invoice ID to shop it in OpenERP
            if err.faultCode == 102:
                _logger.debug('Invoice already exists on Shopware for '
                              'sale order with shopware id %s, trying to find '
                              'the invoice id.',
                              shopware_order.shopware_id)
                shopware_id = self._get_existing_invoice(shopware_order)
                if shopware_id is None:
                    # In that case, we let the exception bubble up so
                    # the user is informed of the 102 error.
                    # We couldn't find the invoice supposedly existing
                    # so an investigation may be necessary.
                    raise
            else:
                raise
        # When the invoice already exists on Shopware, it may return
        # a 102 error (handled above) or return silently without ID
        if not shopware_id:
            # If Shopware returned no ID, try to find the Shopware
            # invoice, but if we don't find it, let consider the job
            # as done, because Shopware did not raised an error
            shopware_id = self._get_existing_invoice(shopware_order)

        if shopware_id:
            self.binder.bind(shopware_id, binding_id)

    def _get_existing_invoice(self, shopware_order):
        invoices = self.backend_adapter.search_read(
            order_id=shopware_order.shopware_order_id)
        if not invoices:
            return
        if len(invoices) > 1:
            return
        return invoices[0]['increment_id']


ShopwareInvoiceSynchronizer = ShopwareInvoiceExporter  # deprecated


@on_invoice_validated
@on_invoice_paid
def invoice_create_bindings(session, model_name, record_id):
    """
    Create a ``shopware.account.invoice`` record. This record will then
    be exported to Shopware.
    """
    invoice = session.env[model_name].browse(record_id)
    # find the shopware shop to retrieve the backend
    # we use the shop as many sale orders can be related to an invoice
    for sale in invoice.sale_ids:
        for shopware_sale in sale.shopware_bind_ids:
            binding_exists = False
            for mag_inv in invoice.shopware_bind_ids:
                if mag_inv.backend_id.id == shopware_sale.backend_id.id:
                    binding_exists = True
                    break
            if binding_exists:
                continue
            # Check if invoice state matches configuration setting
            # for when to export an invoice
            shopware_shop = shopware_sale.shop_id
            payment_method = sale.payment_method_id
            if payment_method and payment_method.create_invoice_on:
                create_invoice = payment_method.create_invoice_on
            else:
                create_invoice = shopware_shop.create_invoice_on

            if create_invoice == invoice.state:
                session.env['shopware.account.invoice'].create({
                    'backend_id': shopware_sale.backend_id.id,
                    'openerp_id': invoice.id,
                    'shopware_order_id': shopware_sale.id})


@on_record_create(model_names='shopware.account.invoice')
def delay_export_account_invoice(session, model_name, record_id, vals):
    """
    Delay the job to export the shopware invoice.
    """
    export_invoice.delay(session, model_name, record_id)


@job(default_channel='root.shopware')
@related_action(action=unwrap_binding)
def export_invoice_paid(session, model_name, record_id):
    """ Deprecated in 2.1.0.dev0. """
    _logger.warning('Deprecated: the export_invoice_paid() job is deprecated '
                    'in favor of export_invoice()')
    return export_invoice(session, model_name, record_id)


@job(default_channel='root.shopware')
@related_action(action=unwrap_binding)
def export_invoice(session, model_name, record_id):
    """ Export a validated or paid invoice. """
    invoice = session.env[model_name].browse(record_id)
    backend_id = invoice.backend_id.id
    env = get_environment(session, model_name, backend_id)
    invoice_exporter = env.get_connector_unit(ShopwareInvoiceExporter)
    return invoice_exporter.run(record_id)
