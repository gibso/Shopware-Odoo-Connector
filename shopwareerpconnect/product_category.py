# -*- coding: utf-8 -*-
##############################################################################
#
#    Author: Guewen Baconnier
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
import pytz
from openerp import models, fields
from openerp.addons.connector.unit.mapper import (mapping,
                                                  ImportMapper
                                                  )
from openerp.addons.connector.exception import (IDMissingInBackend,
                                                MappingError,
                                                )
from .unit.backend_adapter import GenericAdapter
from .unit.import_synchronizer import (DelayedBatchImporter,
                                       ShopwareImporter,
                                       TranslationImporter,
                                       AddCheckpoint,
                                       )
from .backend import shopware

_logger = logging.getLogger(__name__)


class ShopwareProductCategory(models.Model):
    _name = 'shopware.product.category'
    _inherit = 'shopware.binding'
    _inherits = {'product.category': 'openerp_id'}
    _description = 'Shopware Product Category'

    openerp_id = fields.Many2one(comodel_name='product.category',
                                 string='Product Category',
                                 required=True,
                                 ondelete='cascade')
    shopware_parent_id = fields.Many2one(
        comodel_name='shopware.product.category',
        string='Shopware Parent Category',
        ondelete='cascade',
    )
    shopware_child_ids = fields.One2many(
        comodel_name='shopware.product.category',
        inverse_name='shopware_parent_id',
        string='Shopware Child Categories',
    )


class ProductCategory(models.Model):
    _inherit = 'product.category'

    shopware_bind_ids = fields.One2many(
        comodel_name='shopware.product.category',
        inverse_name='openerp_id',
        string="Shopware Bindings",
    )


@shopware
class ProductCategoryAdapter(GenericAdapter):
    _model_name = 'shopware.product.category'
    _shopware_model = 'categories'

    def search(self, filters=None, from_date=None, to_date=None):
        """ Search records according to some criteria and return a
        list of ids

        :rtype: list
        """
        if filters is None:
            filters = {}

        if self.backend_record.write_uid.tz:
            local_tz = pytz.timezone(self.backend_record.write_uid.tz)
            if from_date is not None:
                from_date = from_date.replace(tzinfo=pytz.UTC).astimezone(local_tz)
            if to_date is not None:
                to_date = to_date.replace(tzinfo=pytz.UTC, microsecond=0).astimezone(local_tz)

        if from_date is not None:
            filters[0] = {
                'property': 'changed',
                'expression': '>=',
                'value': from_date.isoformat()
            }
        if to_date is not None:
            filters[1] = {
                'property': 'changed',
                'expression': '<=',
                'value': to_date.isoformat()
            }

        return self._call('%sSearch' % self._shopware_model,
                          {'filter': filters} if filters else {})

    def move(self, categ_id, parent_id, after_categ_id=None):
        return self._call('%s.move' % self._shopware_model,
                          [categ_id, parent_id, after_categ_id])

    def get_assigned_product(self, categ_id):
        return self._call('%s.assignedProducts' % self._shopware_model,
                          [categ_id])

    def assign_product(self, categ_id, product_id, position=0):
        return self._call('%s.assignProduct' % self._shopware_model,
                          [categ_id, product_id, position, 'id'])

    def update_product(self, categ_id, product_id, position=0):
        return self._call('%s.updateProduct' % self._shopware_model,
                          [categ_id, product_id, position, 'id'])

    def remove_product(self, categ_id, product_id):
        return self._call('%s.removeProduct' % self._shopware_model,
                          [categ_id, product_id, 'id'])


@shopware
class ProductCategoryBatchImporter(DelayedBatchImporter):
    """ Import the Shopware Product Categories.

    For every product category in the list, a delayed job is created.
    A priority is set on the jobs according to their level to rise the
    chance to have the top level categories imported first.
    """
    _model_name = ['shopware.product.category']

    def _import_record(self, shopware_id, priority=None):
        """ Delay a job for the import """
        super(ProductCategoryBatchImporter, self)._import_record(
            shopware_id, priority=priority)

    def run(self, filters=None):
        """ Run the synchronization """
        from_date = filters.pop('from_date', None)
        to_date = filters.pop('to_date', None)
        if from_date or to_date:
            updated_ids = self.backend_adapter.search(filters,
                                                      from_date=from_date,
                                                      to_date=to_date)
        else:
            updated_ids = None

        highest_id = max(updated_ids)
        for record_id in updated_ids:
            self._import_record(record_id, priority=highest_id-record_id)


ProductCategoryBatchImport = ProductCategoryBatchImporter  # deprecated


@shopware
class ProductCategoryImporter(ShopwareImporter):
    _model_name = ['shopware.product.category']

    def _import_dependencies(self):
        """ Import the dependencies for the record"""
        record = self.shopware_record
        # import parent category
        # the root category has a 0 parent_id
        if record.get('parentId'):
            parent_id = record['parentId']
            if self.binder.to_openerp(parent_id) is None:
                importer = self.unit_for(ShopwareImporter)
                importer.run(parent_id)

    def _create(self, data):
        openerp_binding = super(ProductCategoryImporter, self)._create(data)
        checkpoint = self.unit_for(AddCheckpoint)
        checkpoint.run(openerp_binding.id)
        return openerp_binding

    def _after_import(self, binding):
        """ Hook called at the end of the import """
        translation_importer = self.unit_for(TranslationImporter)
        translation_importer.run(self.shopware_id, binding.id)


ProductCategoryImport = ProductCategoryImporter  # deprecated


@shopware
class ProductCategoryImportMapper(ImportMapper):
    _model_name = 'shopware.product.category'

    direct = [
        ('name', 'name')
    ]

    @mapping
    def shopware_id(self, record):
        return {'shopware_id': record['id']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def parent_id(self, record):
        if not record.get('parentId'):
            return
        binder = self.binder_for()
        category_id = binder.to_openerp(record['parentId'], unwrap=True)
        sw_cat_id = binder.to_openerp(record['parentId'])

        if category_id is None:
            raise MappingError("The product category with "
                               "shopware id %s is not imported." %
                               record['parentId'])
        return {'parent_id': category_id, 'shopware_parent_id': sw_cat_id}
