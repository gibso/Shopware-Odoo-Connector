# -*- coding: utf-8 -*-
##############################################################################
#
#    Authors: Guewen Baconnier, Oliver Görtz
#    Copyright 2013 Camptocamp SA, Oliver Görtz
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

from openerp import models, fields
from openerp.addons.connector.unit.mapper import (mapping,
                                                  only_create,
                                                  ImportMapper
                                                  )
from .unit.backend_adapter import GenericAdapter
from .unit.import_synchronizer import DelayedBatchImporter
from .backend import shopware


class ResPartnerCategory(models.Model):
    _inherit = 'res.partner.category'

    shopware_bind_ids = fields.One2many(
        comodel_name='shopware.res.partner.category',
        inverse_name='openerp_id',
        string='Shopware Bindings',
        readonly=True,
    )


class ShopwareResPartnerCategory(models.Model):
    _name = 'shopware.res.partner.category'
    _inherit = 'shopware.binding'
    _inherits = {'res.partner.category': 'openerp_id'}

    openerp_id = fields.Many2one(comodel_name='res.partner.category',
                                 string='Partner Category',
                                 required=True,
                                 ondelete='cascade')
    # TODO : replace by a m2o when tax class will be implemented
    # tax_class_id = fields.Integer(string='Tax Class ID')


@shopware
class PartnerCategoryAdapter(GenericAdapter):
    _model_name = 'shopware.res.partner.category'
    _shopware_model = 'CustomerGroups'


@shopware
class PartnerCategoryBatchImporter(DelayedBatchImporter):
    """ Delay import of the records """
    _model_name = ['shopware.res.partner.category']


PartnerCategoryBatchImport = PartnerCategoryBatchImporter  # deprecated


@shopware
class PartnerCategoryImportMapper(ImportMapper):
    _model_name = 'shopware.res.partner.category'

    direct = [
        ('key', 'name'),
        #TODO: find a similar field in Shopware
        # ('tax_class_id', 'tax_class_id'),
    ]

    @mapping
    def shopware_id(self, record):
        return {'shopware_id': record['id']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @only_create
    @mapping
    def openerp_id(self, record):
        """ Will bind the category on a existing one with the same name."""
        existing = self.env['res.partner.category'].search(
            [('name', '=', record['key'])],
            limit=1,
        )
        if existing:
            return {'openerp_id': existing.id}
