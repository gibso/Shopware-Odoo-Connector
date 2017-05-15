# -*- coding: utf-8 -*-
##############################################################################
#
#    Author: Guewen Baconnier, David Beal
#    Copyright 2013 Camptocamp SA
#    Copyright 2013 Akretion
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
import urllib2
import base64
import xmlrpclib
import sys
import pytz
from collections import defaultdict
from openerp import models, fields, api, _
from openerp.addons.connector.queue.job import job, related_action
from openerp.addons.connector.event import on_record_write
from openerp.addons.connector.unit.synchronizer import (Importer,
                                                        Exporter,
                                                        )
from openerp.addons.connector.exception import (MappingError,
                                                InvalidDataError,
                                                IDMissingInBackend
                                                )
from openerp.addons.connector.unit.mapper import (mapping,
                                                  ImportMapper,
                                                  )
from .unit.backend_adapter import (GenericAdapter,
                                   MAGENTO_DATETIME_FORMAT,
                                   )
from .unit.mapper import normalize_datetime
from .unit.import_synchronizer import (DelayedBatchImporter,
                                       ShopwareImporter,
                                       TranslationImporter,
                                       AddCheckpoint,
                                       import_record
                                       )
from .connector import get_environment
from .backend import shopware
from .related_action import unwrap_binding

_logger = logging.getLogger(__name__)


def chunks(items, length):
    for index in xrange(0, len(items), length):
        yield items[index:index + length]


class ShopwareArticle(models.Model):
    _name = 'shopware.article'
    _inherit = 'shopware.binding'
    _description = 'Shopware Article'

    shopware_product_ids = fields.One2many(
        comodel_name='shopware.product.product',
        inverse_name='shopware_article_id',
        string='Shopware Products'
    )
    changed = fields.Date('Changed (on Shopware)')
    name = fields.Char(string='Article Name', required=True)
    description = fields.Char(string='Article Description')
    description_long = fields.Char(string='Article Description Long')
    active = fields.Boolean()
    categ_id = fields.Many2one(
        'product.category',
        required=True,
        change_default=True,
        domain="[('type','=','normal')]"
    )
    categ_ids = fields.Many2many(
        'product.category',
        required=True,
        change_default=True,
        domain="[('type','=','normal')]"
    )


class ShopwareProductProduct(models.Model):
    _name = 'shopware.product.product'
    _inherit = 'shopware.binding'
    _inherits = {'product.product': 'openerp_id'}
    _description = 'Shopware Product'

    openerp_id = fields.Many2one(comodel_name='product.product',
                                 string='Product',
                                 required=True,
                                 ondelete='restrict')
    shopware_article_id = fields.Many2one(
        comodel_name='shopware.article',
        string='Shopware Article',
        required=True,
        ondelete='cascade'
    )
    # XXX shop_ids can be computed from categories
    shop_ids = fields.Many2many(comodel_name='shopware.shop',
                                   string='Shops',
                                   readonly=True)
    changed = fields.Date('Changed (on Shopware)')
    manage_stock = fields.Selection(
        selection=[('use_default', 'Use Default Config'),
                   ('no', 'Do Not Manage Stock'),
                   ('yes', 'Manage Stock')],
        string='Manage Stock Level',
        default='use_default',
        required=True,
    )
    backorders = fields.Selection(
        selection=[('use_default', 'Use Default Config'),
                   ('no', 'No Sell'),
                   ('yes', 'Sell Quantity < 0'),
                   ('yes-and-notification', 'Sell Quantity < 0 and '
                                            'Use Customer Notification')],
        string='Manage Inventory Backorders',
        default='use_default',
        required=True,
    )
    shopware_qty = fields.Float(string='Computed Quantity',
                               help="Last computed quantity to send "
                                    "on Shopware.")
    no_stock_sync = fields.Boolean(
        string='No Stock Synchronization',
        required=False,
        help="Check this to exclude the product "
             "from stock synchronizations.",
    )

    RECOMPUTE_QTY_STEP = 1000  # products at a time

    @api.multi
    def recompute_shopware_qty(self):
        """ Check if the quantity in the stock location configured
        on the backend has changed since the last export.

        If it has changed, write the updated quantity on `shopware_qty`.
        The write on `shopware_qty` will trigger an `on_record_write`
        event that will create an export job.

        It groups the products by backend to avoid to read the backend
        informations for each product.
        """
        # group products by backend
        backends = defaultdict(self.browse)
        for product in self:
            backends[product.backend_id] |= product

        for backend, products in backends.iteritems():
            self._recompute_shopware_qty_backend(backend, products)
        return True

    @api.multi
    def _recompute_shopware_qty_backend(self, backend, products,
                                       read_fields=None):
        """ Recompute the products quantity for one backend.

        If field names are passed in ``read_fields`` (as a list), they
        will be read in the product that is used in
        :meth:`~._shopware_qty`.

        """
        if backend.product_stock_field_id:
            stock_field = backend.product_stock_field_id.name
        else:
            stock_field = 'virtual_available'

        location = backend.warehouse_id.lot_stock_id

        product_fields = ['shopware_qty', stock_field]
        if read_fields:
            product_fields += read_fields

        self_with_location = self.with_context(location=location.id)
        for chunk_ids in chunks(products.ids, self.RECOMPUTE_QTY_STEP):
            records = self_with_location.browse(chunk_ids)
            for product in records.read(fields=product_fields):
                new_qty = self._shopware_qty(product,
                                            backend,
                                            location,
                                            stock_field)
                if new_qty != product['shopware_qty']:
                    self.browse(product['id']).shopware_qty = new_qty

    @api.multi
    def _shopware_qty(self, product, backend, location, stock_field):
        """ Return the current quantity for one product.

        Can be inherited to change the way the quantity is computed,
        according to a backend / location.

        If you need to read additional fields on the product, see the
        ``read_fields`` argument of :meth:`~._recompute_shopware_qty_backend`

        """
        return product[stock_field]


class ProductProduct(models.Model):
    _inherit = 'product.product'

    shopware_bind_ids = fields.One2many(
        comodel_name='shopware.product.product',
        inverse_name='openerp_id',
        string='Shopware Bindings',
    )


@shopware
class ArticleAdapter(GenericAdapter):
    _model_name = 'shopware.article'
    _shopware_model = 'articles'

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

        return super(ArticleAdapter, self).search(filters)



@shopware
class ProductProductAdapter(GenericAdapter):
    _model_name = 'shopware.product.product'
    _shopware_model = 'variants'

    def search(self, filters=None, from_date=None, to_date=None):
        """ Search records according to some criteria
        and returns a list of ids

        :rtype: list
        """
        if filters is None:
            filters = {}
        dt_fmt = MAGENTO_DATETIME_FORMAT
        if from_date is not None:
            filters.setdefault('updated_at', {})
            filters['updated_at']['from'] = from_date.strftime(dt_fmt)
        if to_date is not None:
            filters.setdefault('updated_at', {})
            filters['updated_at']['to'] = to_date.strftime(dt_fmt)
        # TODO add a search entry point on the Shopware API
        return [int(row['product_id']) for row
                in self._call('%s.list' % self._shopware_model,
                              [filters] if filters else [{}])]

    def write(self, id, data, shop_id=None):
        """ Update records on the external system """
        # XXX actually only ol_catalog_product.update works
        # the PHP connector maybe breaks the catalog_product.update
        return self._call('ol_catalog_product.update',
                          [int(id), data, shop_id, 'id'])

    def get_images(self, id, shop_id=None):
        return self._call('product_media.list', [int(id), shop_id, 'id'])

    def read_image(self, id, image_name, shop_id=None):
        return self._call('product_media.info',
                          [int(id), image_name, shop_id, 'id'])

    def update_inventory(self, id, data):
        return self._call('%s/%d' % (self._shopware_model, int(id)), data, 'PUT')

@shopware
class ArticleBatchImporter(DelayedBatchImporter):
    """ Import the Shopware Articles.  """
    _model_name = ['shopware.article']

    def run(self, filters=None):
        """ Run the synchronization """
        from_date = filters.pop('from_date', None)
        to_date = filters.pop('to_date', None)
        record_ids = self.backend_adapter.search(filters,
                                                 from_date=from_date,
                                                 to_date=to_date)
        _logger.info('search for shopware products %s returned %s',
                     filters, record_ids)
        for record_id in record_ids:
            self._import_record(record_id)


@shopware
class CatalogImageImporter(Importer):
    """ Import images for a record.

    Usually called from importers, in ``_after_import``.
    For instance from the products importer.
    """

    _model_name = ['shopware.product.product',
                   ]

    def _get_images(self, shop_id=None):
        return self.backend_adapter.get_images(self.shopware_id, shop_id)

    def _sort_images(self, images):
        """ Returns a list of images sorted by their priority.
        An image with the 'image' type is the the primary one.
        The other images are sorted by their position.

        The returned list is reversed, the items at the end
        of the list have the higher priority.
        """
        if not images:
            return {}
        # place the images where the type is 'image' first then
        # sort them by the reverse priority (last item of the list has
        # the the higher priority)

        def priority(image):
            primary = 'image' in image['types']
            try:
                position = int(image['position'])
            except ValueError:
                position = sys.maxint
            return (primary, -position)
        return sorted(images, key=priority)

    def _get_binary_image(self, image_data):
        url = image_data['url'].encode('utf8')
        try:
            request = urllib2.Request(url)
            binary = urllib2.urlopen(request)
        except urllib2.HTTPError as err:
            if err.code == 404:
                # the image is just missing, we skip it
                return
            else:
                # we don't know why we couldn't download the image
                # so we propagate the error, the import will fail
                # and we have to check why it couldn't be accessed
                raise
        else:
            return binary.read()

    def _write_image_data(self, binding_id, binary, image_data):
        model = self.model.with_context(connector_no_export=True)
        binding = model.browse(binding_id)
        binding.write({'image': base64.b64encode(binary)})

    def run(self, shopware_id, binding_id):
        self.shopware_id = shopware_id
        images = self._get_images()
        images = self._sort_images(images)
        binary = None
        image_data = None
        while not binary and images:
            image_data = images.pop()
            binary = self._get_binary_image(image_data)
        if not binary:
            return
        self._write_image_data(binding_id, binary, image_data)


@shopware
class BundleImporter(Importer):
    """ Can be inherited to change the way the bundle products are
    imported.

    Called at the end of the import of a product.

    Example of action when importing a bundle product:
        - Create a bill of material
        - Import the structure of the bundle in new objects

    By default, the bundle products are not imported: the jobs
    are set as failed, because there is no known way to import them.
    An additional module that implements the import should be installed.

    If you want to create a custom importer for the bundles, you have to
    declare the ConnectorUnit on your backend::

        @shopware_custom
        class XBundleImporter(BundleImporter):
            _model_name = 'shopware.product.product'

            # implement import_bundle

    If you want to create a generic module that import bundles, you have
    to replace the current ConnectorUnit::

        @shopware(replacing=BundleImporter)
        class XBundleImporter(BundleImporter):
            _model_name = 'shopware.product.product'

            # implement import_bundle

    And to add the bundle type in the supported product types::

        class shopware_product_product(orm.Model):
            _inherit = 'shopware.product.product'

            def product_type_get(self, cr, uid, context=None):
                types = super(shopware_product_product, self).product_type_get(
                    cr, uid, context=context)
                if 'bundle' not in [item[0] for item in types]:
                    types.append(('bundle', 'Bundle'))
                return types

    """
    _model_name = 'shopware.product.product'

    def run(self, binding_id, shopware_record):
        """ Import the bundle information about a product.

        :param shopware_record: product information from Shopware
        """


@shopware
class ArticleImportMapper(ImportMapper):
    _model_name = 'shopware.article'

    direct = [('name', 'name'),
              ('description', 'description'),
              ('descriptionLong', 'description_long'),
              ('active', 'active'),
              ('id', 'shopware_id'),
              (normalize_datetime('changed'), 'changed')]


    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def categories(self, record):
        sw_categories = record['categories']
        binder = self.binder_for('shopware.product.category')

        category_ids = []
        main_categ_id = None

        for sw_category in sw_categories:
            cat_id = binder.to_openerp(sw_category['id'], unwrap=True)
            if cat_id is None:
                raise MappingError("The product category with "
                                   "shopware id %s is not imported." %
                                   sw_category['id'])

            category_ids.append(cat_id)

        if category_ids:
            main_categ_id = category_ids.pop(0)

        if main_categ_id is None:
            default_categ = self.backend_record.default_category_id
            if default_categ:
                main_categ_id = default_categ.id

        result = {'categ_ids': [(6, 0, category_ids)]}
        if main_categ_id:  # OpenERP assign 'All Products' if not specified
            result['categ_id'] = main_categ_id
        return result


@shopware
class ProductImportMapper(ImportMapper):
    _model_name = 'shopware.product.product'

    direct = [('number', 'default_code'),
              ('additionalText', 'description_sale'),
              ('active', 'active'),
              ('ean', 'ean13'),
              ('weight', 'weight'),
              ('articleId', 'shopware_article_id')]

    @mapping
    def price(self, record):
        # only import the EK price, because this one always exists
        prices = record['prices']

        for price in prices:
            if price['from'] == 1 and price['customerGroup']['key'] == 'EK':
                return {'list_price': price['price']}

        raise MappingError("Could not store the price for the article detail with shopware id %s"
                           % record['id'])

    @mapping
    def shopware_article(self, record):

        article = self.env['shopware.article'].search(
            [('shopware_id', '=', record['articleId'])]
        )
        if article is None:
            raise MappingError("The shopware article with "
                               "shopware id %s does not exist" %
                               record['articleId'])

        category_ids = []
        for category in article.categ_ids:
            category_ids.append(category.id)

        return {
            'name': article.name,
            'description': article.description_long,
            'shopware_article_id': article.id,
            'categ_ids': [(6, 0, category_ids)],
            'categ_id': article.categ_id.id,
            'changed': article.changed
        }

    @mapping
    def shopware_id(self, record):
        return {'shopware_id': record['id']}

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}


@shopware
class ArticleImporter(ShopwareImporter):
    _model_name = ['shopware.article']

    _base_mapper = ArticleImportMapper

    def _import_dependencies(self):
        """ Import the dependencies for the record"""
        record = self.shopware_record
        for sw_category in record['categories']:
            self._import_dependency(sw_category['id'],
                                    'shopware.product.category')

    def _after_import(self, binding):
        """ Hook called at the end of the import """

        record = self.shopware_record
        product_model = 'shopware.product.product'

        # create batchjob for the main detail
        sw_main_detail_id = record['mainDetail']['id']
        import_record.delay(self.session, product_model, self.backend_record.id, sw_main_detail_id)

        # create batchjob for the remaining details
        for sw_detail in record['details']:
            import_record.delay(self.session, product_model, self.backend_record.id, sw_detail['id'])


@shopware
class ProductImporter(ShopwareImporter):
    _model_name = ['shopware.product.product']

    _base_mapper = ProductImportMapper

    def _import_dependencies(self):
        """ Import the dependencies for the record"""
        record = self.shopware_record
        # import related article
        self._import_dependency(record['articleId'], 'shopware.article')

    def _create(self, data):
        openerp_binding = super(ProductImporter, self)._create(data)
        checkpoint = self.unit_for(AddCheckpoint)
        checkpoint.run(openerp_binding.id)
        return openerp_binding


ProductImport = ProductImporter  # deprecated


@shopware
class PriceProductImportMapper(ImportMapper):
    _model_name = 'shopware.product.product'

    @mapping
    def price(self, record):
        return {'list_price': record.get('price', 0.0)}


@shopware
class IsActiveProductImportMapper(ImportMapper):
    _model_name = 'shopware.product.product'

    @mapping
    def is_active(self, record):
        """Check if the product is active in Shopware
        and set active flag in OpenERP
        status == 1 in Shopware means active"""
        return {'active': (record.get('status') == '1')}


@shopware
class BundleProductImportMapper(ImportMapper):
    _model_name = 'shopware.product.product'


@shopware
class ProductInventoryExporter(Exporter):
    _model_name = ['shopware.product.product']

    _map_backorders = {'use_default': 0,
                       'no': 0,
                       'yes': 1,
                       'yes-and-notification': 2,
                       }

    def _get_data(self, product, fields):
        result = {}
        if 'shopware_qty' in fields:
            result.update({
                'inStock': product.shopware_qty
            })
        if 'manage_stock' in fields:
            manage = product.manage_stock
            result.update({
                'manage_stock': int(manage == 'yes'),
                'use_config_manage_stock': int(manage == 'use_default'),
            })
        if 'backorders' in fields:
            backorders = product.backorders
            result.update({
                'backorders': self._map_backorders[backorders],
                'use_config_backorders': int(backorders == 'use_default'),
            })
        return result

    def run(self, binding_id, fields):
        """ Export the product inventory to Shopware """
        product = self.model.browse(binding_id)
        shopware_id = self.binder.to_backend(product.id)
        data = self._get_data(product, fields)
        self.backend_adapter.update_inventory(shopware_id, data)


ProductInventoryExport = ProductInventoryExporter  # deprecated


# fields which should not trigger an export of the products
# but an export of their inventory
INVENTORY_FIELDS = ('manage_stock',
                    'backorders',
                    'shopware_qty',
                    )


@on_record_write(model_names='shopware.product.product')
def shopware_product_modified(session, model_name, record_id, vals):
    if session.context.get('connector_no_export'):
        return
    if session.env[model_name].browse(record_id).no_stock_sync:
        return
    inventory_fields = list(set(vals).intersection(INVENTORY_FIELDS))
    if inventory_fields:
        export_product_inventory.delay(session, model_name,
                                       record_id, fields=inventory_fields,
                                       priority=20)


@job(default_channel='root.shopware')
@related_action(action=unwrap_binding)
def export_product_inventory(session, model_name, record_id, fields=None):
    """ Export the inventory configuration and quantity of a product. """
    product = session.env[model_name].browse(record_id)
    backend_id = product.backend_id.id
    env = get_environment(session, model_name, backend_id)
    inventory_exporter = env.get_connector_unit(ProductInventoryExporter)
    return inventory_exporter.run(record_id, fields)
