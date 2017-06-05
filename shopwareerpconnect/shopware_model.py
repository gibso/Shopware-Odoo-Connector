# -*- coding: utf-8 -*-
##############################################################################
#
#    Authors: Guewen Baconnier, Oliver Görtz
#    Copyright 2013 Camptocamp SA, Oliver Görtz
#    Copyright 2013 Akretion, Oliver Görtz
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
from datetime import datetime, timedelta
from openerp import models, fields, api, _
from openerp.exceptions import Warning as UserError
from openerp.addons.connector.session import ConnectorSession
from openerp.addons.connector.connector import ConnectorUnit
from openerp.addons.connector.unit.mapper import mapping, ImportMapper
from .unit.backend_adapter import GenericAdapter
from .unit.import_synchronizer import (import_batch,
                                       DirectBatchImporter,
                                       ShopwareImporter,
                                       )
from .partner import partner_import_batch
from .sale import sale_order_import_batch
from .backend import shopware
from .connector import add_checkpoint

_logger = logging.getLogger(__name__)

IMPORT_DELTA_BUFFER = 30  # seconds


class ShopwareBackend(models.Model):
    _name = 'shopware.backend'
    _description = 'Shopware Backend'
    _inherit = 'connector.backend'

    _backend_type = 'shopware'

    @api.model
    def select_versions(self):
        """ Available versions in the backend.

        Can be inherited to add custom versions.  Using this method
        to add a version from an ``_inherit`` does not constrain
        to redefine the ``version`` field in the ``_inherit`` model.
        """
        return [('5.2', '5.2+')]

    @api.model
    def _get_stock_field_id(self):
        field = self.env['ir.model.fields'].search(
            [('model', '=', 'product.product'),
             ('name', '=', 'virtual_available')],
            limit=1)
        return field

    version = fields.Selection(selection='select_versions', required=True)
    location = fields.Char(
        string='Location',
        required=True,
        help="Url to shopware application",
    )
    username = fields.Char(
        string='Username',
        help="Webservice user",
    )
    token = fields.Char(
        string='API key',
        help="Webservice API key",
    )
    sale_prefix = fields.Char(
        string='Sale Prefix',
        help="A prefix put before the name of imported sales orders.\n"
             "For instance, if the prefix is 'mag-', the sales "
             "order 100000692 in Shopware, will be named 'mag-100000692' "
             "in OpenERP.",
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        required=True,
        help='Warehouse used to compute the '
             'stock quantities.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='warehouse_id.company_id',
        string='Company',
        readonly=True,
    )
    shop_ids = fields.One2many(
        comodel_name='shopware.shop',
        inverse_name='backend_id',
        string='Shop',
        readonly=True,
    )
    default_lang_id = fields.Many2one(
        comodel_name='res.lang',
        string='Default Language',
        help="If a default language is selected, the records "
             "will be imported in the translation of this language.\n"
             "Note that a similar configuration exists "
             "for each shop.",
    )
    default_category_id = fields.Many2one(
        comodel_name='product.category',
        string='Default Product Category',
        help='If a default category is selected, products imported '
             'without a category will be linked to it.',
    )

    # TODO? add a field `auto_activate` -> activate a cron
    import_products_from_date = fields.Datetime(
        string='Import products from date',
    )
    import_categories_from_date = fields.Datetime(
        string='Import categories from date',
    )
    product_stock_field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Stock Field',
        default=_get_stock_field_id,
        domain="[('model', 'in', ['product.product', 'product.template']),"
               " ('ttype', '=', 'float')]",
        help="Choose the field of the product which will be used for "
             "stock inventory updates.\nIf empty, Quantity Available "
             "is used.",
    )
    product_binding_ids = fields.One2many(
        comodel_name='shopware.product.product',
        inverse_name='backend_id',
        string='Shopware Products',
        readonly=True,
    )
    account_analytic_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic account',
        help='If specified, this analytic account will be used to fill the '
        'field  on the sale order created by the connector. The value can '
        'also be specified on shop or the shop or the shop view.'
    )
    fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string='Fiscal position',
        help='If specified, this fiscal position will be used to fill the '
        'field fiscal position on the sale order created by the connector.'
        'The value can also be specified on shop or the shop or the '
        'shop view.'
    )

    _sql_constraints = [
        ('sale_prefix_uniq', 'unique(sale_prefix)',
         "A backend with the same sale prefix already exists")
    ]

    @api.multi
    def check_shopware_structure(self):
        """ Used in each data import.

        Verify if a shop exists for each backend before starting the import.
        """
        for backend in self:
            shops = backend.shop_ids
            if not shops:
                backend.synchronize_metadata()
        return True

    @api.multi
    def synchronize_metadata(self):
        try:
            session = ConnectorSession.from_env(self.env)
            for backend in self:
                for model in ('shopware.shop',
                              'shopware.shop',
                              'shopware.shop'):
                    # import directly, do not delay because this
                    # is a fast operation, a direct return is fine
                    # and it is simpler to import them sequentially
                    import_batch(session, model, backend.id)
            return True
        except Exception as e:
            _logger.error(e.message, exc_info=True)
            raise UserError(
                _(u"Check your configuration, we can't get the data. "
                  u"Here is the error:\n%s") %
                str(e).decode('utf-8', 'ignore'))

    @api.multi
    def import_partners(self):
        """ Import partners from all shops """
        for backend in self:
            backend.check_shopware_structure()
            backend.shop_ids.import_partners()
        return True

    @api.multi
    def import_sale_orders(self):
        """ Import sale orders from all shop views """
        shop_obj = self.env['shopware.shop']
        shops = shop_obj.search([('backend_id', 'in', self.ids)])
        shops.import_sale_orders()
        return True

    @api.multi
    def import_customer_groups(self):
        session = ConnectorSession(self.env.cr, self.env.uid,
                                   context=self.env.context)
        for backend in self:
            backend.check_shopware_structure()
            import_batch.delay(session, 'shopware.res.partner.category',
                               backend.id)

        return True

    @api.multi
    def _import_from_date(self, model, from_date_field):
        session = ConnectorSession(self.env.cr, self.env.uid,
                                   context=self.env.context)
        import_start_time = datetime.now()
        for backend in self:
            backend.check_shopware_structure()
            from_date = getattr(backend, from_date_field)
            if from_date:
                from_date = fields.Datetime.from_string(from_date)
            else:
                from_date = None
            import_batch.delay(session, model,
                               backend.id,
                               filters={'from_date': from_date,
                                        'to_date': import_start_time})
        # Records from Shopware are imported based on their `created_at`
        # date.  This date is set on Shopware at the beginning of a
        # transaction, so if the import is run between the beginning and
        # the end of a transaction, the import of a record may be
        # missed.  That's why we add a small buffer back in time where
        # the eventually missed records will be retrieved.  This also
        # means that we'll have jobs that import twice the same records,
        # but this is not a big deal because they will be skipped when
        # the last `sync_date` is the same.
        next_time = import_start_time - timedelta(seconds=IMPORT_DELTA_BUFFER)
        next_time = fields.Datetime.to_string(next_time)
        self.write({from_date_field: next_time})

    @api.multi
    def import_product_categories(self):
        self._import_from_date('shopware.product.category',
                               'import_categories_from_date')
        return True

    @api.multi
    def import_articles(self):
        self._import_from_date('shopware.article',
                               'import_products_from_date')
        return True

    @api.multi
    def _domain_for_update_product_stock_qty(self):
        return [
            ('backend_id', 'in', self.ids),
            ('type', '!=', 'service'),
            ('no_stock_sync', '=', False),
        ]

    @api.multi
    def update_product_stock_qty(self):
        mag_product_obj = self.env['shopware.product.product']
        domain = self._domain_for_update_product_stock_qty()
        shopware_products = mag_product_obj.search(domain)
        shopware_products.recompute_shopware_qty()
        return True

    @api.model
    def _shopware_backend(self, callback, domain=None):
        if domain is None:
            domain = []
        backends = self.search(domain)
        if backends:
            getattr(backends, callback)()

    @api.model
    def _scheduler_import_sale_orders(self, domain=None):
        self._shopware_backend('import_sale_orders', domain=domain)

    @api.model
    def _scheduler_import_customer_groups(self, domain=None):
        self._shopware_backend('import_customer_groups', domain=domain)

    @api.model
    def _scheduler_import_partners(self, domain=None):
        self._shopware_backend('import_partners', domain=domain)

    @api.model
    def _scheduler_import_product_categories(self, domain=None):
        self._shopware_backend('import_product_categories', domain=domain)

    @api.model
    def _scheduler_import_product_product(self, domain=None):
        self._shopware_backend('import_product_product', domain=domain)

    @api.model
    def _scheduler_update_product_stock_qty(self, domain=None):
        self._shopware_backend('update_product_stock_qty', domain=domain)

    @api.multi
    def output_recorder(self):
        """ Utility method to output a file containing all the recorded
        requests / responses with Shopware.  Used to generate test data.
        Should be called with ``erppeek`` for instance.
        """
        from .unit.backend_adapter import output_recorder
        import os
        import tempfile
        fmt = '%Y-%m-%d-%H-%M-%S'
        timestamp = datetime.now().strftime(fmt)
        filename = 'output_%s_%s' % (self.env.cr.dbname, timestamp)
        path = os.path.join(tempfile.gettempdir(), filename)
        output_recorder(path)
        return path


class ShopwareShop(models.Model):
    _name = 'shopware.shop'
    _inherit = ['shopware.binding']
    _description = 'Shopware Shop'
    _parent_name = 'backend_id'

    _order = 'sort_order ASC, id ASC'

    name = fields.Char(required=True, readonly=True)
    enabled = fields.Boolean(string='Enabled', readonly=True)
    sort_order = fields.Integer(string='Sort Order', readonly=True)
    lang_id = fields.Many2one(comodel_name='res.lang', string='Language')
    import_partners_from_date = fields.Datetime(
        string='Import partners from date',
    )
    product_binding_ids = fields.Many2many(
        comodel_name='shopware.product.product',
        string='Shopware Products',
        readonly=True,
    )
    send_picking_done_mail = fields.Boolean(
        string='Send email notification on picking done',
        help="Does the picking export/creation should send "
             "an email notification on Shopware side?",
    )
    send_invoice_paid_mail = fields.Boolean(
        string='Send email notification on invoice validated/paid',
        help="Does the invoice export/creation should send "
             "an email notification on Shopware side?",
    )
    create_invoice_on = fields.Selection(
        selection=[('open', 'Validate'),
                   ('paid', 'Paid')],
        string='Create invoice on action',
        default='paid',
        required=True,
        help="Should the invoice be created in Shopware "
             "when it is validated or when it is paid in OpenERP?\n"
             "This only takes effect if the sales order's related "
             "payment method is not giving an option for this by "
             "itself. (See Payment Methods)",
    )
    section_id = fields.Many2one(comodel_name='crm.case.section',
                                 string='Sales Team')
    import_orders_from_date = fields.Datetime(
        string='Import sale orders from date',
        help='do not consider non-imported sale orders before this date. '
             'Leave empty to import all sale orders',
    )
    no_sales_order_sync = fields.Boolean(
        string='No Sales Order Synchronization',
        help='Check if the shop is active in Shopware '
             'but its sales orders should not be imported.',
    )
    catalog_price_tax_included = fields.Boolean(string='Prices include tax')
    specific_account_analytic_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Specific analytic account',
        help='If specified, this analytic account will be used to fill the '
             'field on the sale order created by the connector. The value can '
             'also be specified on shop or the shop or the shop view.'
    )
    specific_fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string='Specific fiscal position',
        help='If specified, this fiscal position will be used to fill the '
             'field fiscal position on the sale order created by the connector.'
             'The value can also be specified on shop or the shop or the '
             'shop view.'
    )
    account_analytic_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic account',
        compute='_get_account_analytic_id',
    )
    fiscal_position_id = fields.Many2one(
        comodel_name='account.fiscal.position',
        string='Fiscal position',
        compute='_get_fiscal_position_id',
    )

    @property
    def _parent(self):
        return getattr(self, self._parent_name)

    @api.multi
    def _get_account_analytic_id(self):
        for this in self:
            this.account_analytic_id = (
                this.specific_account_analytic_id or
                this._parent.account_analytic_id)

    @api.multi
    def _get_fiscal_position_id(self):
        for this in self:
            this.fiscal_position_id = (
                this.specific_fiscal_position_id or
                this._parent.fiscal_position_id)

    @api.multi
    def import_partners(self):
        session = ConnectorSession(self.env.cr, self.env.uid,
                                   context=self.env.context)
        import_start_time = datetime.now()
        for shop in self:
            backend_id = shop.backend_id.id
            if shop.import_partners_from_date:
                from_string = fields.Datetime.from_string
                from_date = from_string(shop.import_partners_from_date)
            else:
                from_date = None
            partner_import_batch.delay(
                session, 'shopware.res.partner', backend_id,
                {'shopware_shop_id': shop.shopware_id,
                 'from_date': from_date,
                 'to_date': import_start_time})
        # Records from Shopware are imported based on their `created_at`
        # date.  This date is set on Shopware at the beginning of a
        # transaction, so if the import is run between the beginning and
        # the end of a transaction, the import of a record may be
        # missed.  That's why we add a small buffer back in time where
        # the eventually missed records will be retrieved.  This also
        # means that we'll have jobs that import twice the same records,
        # but this is not a big deal because they will be skipped when
        # the last `sync_date` is the same.
        next_time = import_start_time - timedelta(seconds=IMPORT_DELTA_BUFFER)
        next_time = fields.Datetime.to_string(next_time)
        self.write({'import_partners_from_date': next_time})
        return True

    @api.multi
    def import_sale_orders(self):
        session = ConnectorSession(self.env.cr, self.env.uid,
                                   context=self.env.context)
        import_start_time = datetime.now()
        for shop in self:
            if shop.no_sales_order_sync:
                _logger.debug("The shop '%s' is active in Shopware "
                              "but is configured not to import the "
                              "sales orders", shop.name)
                continue
            backend_id = shop.backend_id.id
            if shop.import_orders_from_date:
                from_string = fields.Datetime.from_string
                from_date = from_string(shop.import_orders_from_date)
            else:
                from_date = None
            sale_order_import_batch.delay(
                session,
                'shopware.sale.order',
                backend_id,
                {'shopware_shop_id': shop.shopware_id,
                 'from_date': from_date,
                 'to_date': import_start_time},
                priority=1)  # executed as soon as possible
        # Records from Shopware are imported based on their `created_at`
        # date.  This date is set on Shopware at the beginning of a
        # transaction, so if the import is run between the beginning and
        # the end of a transaction, the import of a record may be
        # missed.  That's why we add a small buffer back in time where
        # the eventually missed records will be retrieved.  This also
        # means that we'll have jobs that import twice the same records,
        # but this is not a big deal because the sales orders will be
        # imported the first time and the jobs will be skipped on the
        # subsequent imports
        next_time = import_start_time - timedelta(seconds=IMPORT_DELTA_BUFFER)
        next_time = fields.Datetime.to_string(next_time)
        self.write({'import_orders_from_date': next_time})
        return True


@shopware
class ShopAdapter(GenericAdapter):
    _model_name = 'shopware.shop'
    _shopware_model = 'shops'


@shopware
class MetadataBatchImporter(DirectBatchImporter):
    """ Import the records directly, without delaying the jobs.

    Import the Shopware Shops

    They are imported directly because this is a rare and fast operation,
    and we don't really bother if it blocks the UI during this time.
    (that's also a mean to rapidly check the connectivity with Shopware).
    """
    _model_name = 'shopware.shop'


MetadataBatchImport = MetadataBatchImporter  # deprecated


@shopware
class ShopImportMapper(ImportMapper):
    _model_name = 'shopware.shop'

    direct = [('name', 'name'),
              ('active', 'enabled'),
              ('position', 'sort_order')]

    @mapping
    def name(self, record):
        name = record['name']
        if name is None:
            name = _('Undefined')
        return {'name': name}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}


@shopware
class ShopAddCheckpoint(ConnectorUnit):
    """ Add a connector.checkpoint on the shopware.shop
    or shopware.shop record
    """
    _model_name = 'shopware.shop'

    def run(self, binding_id):
        add_checkpoint(self.session,
                       self.model._name,
                       binding_id,
                       self.backend_record.id)

# backward compatibility
ShopViewAddCheckpoint = shopware(ShopAddCheckpoint)
