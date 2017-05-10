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
from openerp import models, fields
from openerp.addons.connector.unit.mapper import (mapping,
                                                  ImportMapper
                                                  )
from openerp.addons.connector.exception import (IDMissingInBackend,
                                                MappingError,
                                                )
from .unit.backend_adapter import (GenericAdapter,
                                   MAGENTO_DATETIME_FORMAT,
                                   )
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
    description = fields.Text(translate=True)
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
    _shopware_model = 'catalog_category'
    _admin_path = '/{model}/index/'

    def _call(self, method, arguments):
        try:
            return super(ProductCategoryAdapter, self)._call(method, arguments)
        except xmlrpclib.Fault as err:
            # 101 is the error in the Shopware API
            # when the category does not exist
            if err.faultCode == 102:
                raise IDMissingInBackend
            else:
                raise

    def search(self, filters=None, from_date=None, to_date=None):
        """ Search records according to some criteria and return a
        list of ids

        :rtype: list
        """
        if filters is None:
            filters = {}

        dt_fmt = MAGENTO_DATETIME_FORMAT
        if from_date is not None:
            filters.setdefault('updated_at', {})
            # updated_at include the created records
            filters['updated_at']['from'] = from_date.strftime(dt_fmt)
        if to_date is not None:
            filters.setdefault('updated_at', {})
            filters['updated_at']['to'] = to_date.strftime(dt_fmt)

        return self._call('oerp_catalog_category.search',
                          [filters] if filters else [{}])

    def read(self, id, shop_id=None, attributes=None):
        """ Returns the information of a record

        :rtype: dict
        """
        return self._call('%s.info' % self._shopware_model,
                          [int(id), shop_id, attributes])

    def tree(self, parent_id=None, shop_id=None):
        """ Returns a tree of product categories

        :rtype: dict
        """
        def filter_ids(tree):
            children = {}
            if tree['children']:
                for node in tree['children']:
                    children.update(filter_ids(node))
            category_id = {tree['category_id']: children}
            return category_id
        if parent_id:
            parent_id = int(parent_id)
        tree = self._call('%s.tree' % self._shopware_model,
                          [parent_id, shop_id])
        return filter_ids(tree)

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

        base_priority = 10

        def import_nodes(tree, level=0):
            for node_id, children in tree.iteritems():
                # By changing the priority, the top level category has
                # more chance to be imported before the childrens.
                # However, importers have to ensure that their parent is
                # there and import it if it doesn't exist
                if updated_ids is None or node_id in updated_ids:
                    self._import_record(node_id, priority=base_priority+level)
                import_nodes(children, level=level+1)
        tree = self.backend_adapter.tree()
        import_nodes(tree)


ProductCategoryBatchImport = ProductCategoryBatchImporter  # deprecated


@shopware
class ProductCategoryImporter(ShopwareImporter):
    _model_name = ['shopware.product.category']

    def _import_dependencies(self):
        """ Import the dependencies for the record"""
        record = self.shopware_record
        # import parent category
        # the root category has a 0 parent_id
        if record.get('parent_id'):
            parent_id = record['parent_id']
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
        ('description', 'description'),
    ]

    @mapping
    def name(self, record):
        if record['level'] == '0':  # top level category; has no name
            return {'name': self.backend_record.name}
        if record['name']:  # may be empty in shops
            return {'name': record['name']}

    @mapping
    def shopware_id(self, record):
        return {'shopware_id': record['category_id']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def parent_id(self, record):
        if not record.get('parent_id'):
            return
        binder = self.binder_for()
        category_id = binder.to_openerp(record['parent_id'], unwrap=True)
        mag_cat_id = binder.to_openerp(record['parent_id'])

        if category_id is None:
            raise MappingError("The product category with "
                               "shopware id %s is not imported." %
                               record['parent_id'])
        return {'parent_id': category_id, 'shopware_parent_id': mag_cat_id}
