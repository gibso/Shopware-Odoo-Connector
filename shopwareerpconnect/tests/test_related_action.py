# -*- coding: utf-8 -*-
import mock

import openerp
import openerp.tests.common as common
from openerp.addons.connector.queue.job import (
    Job,
    OpenERPJobStorage,
)
from openerp.addons.connector.session import (
    ConnectorSession)
from .common import mock_api
from .data_base import shopware_base_responses
from ..unit.import_synchronizer import import_batch, import_record
from ..unit.export_synchronizer import export_record


class TestRelatedActionStorage(common.TransactionCase):
    """ Test related actions on shopd jobs """

    def setUp(self):
        super(TestRelatedActionStorage, self).setUp()
        backend_model = self.env['shopware.backend']
        self.session = ConnectorSession(self.env.cr, self.env.uid,
                                        context=self.env.context)
        warehouse = self.env.ref('stock.warehouse0')
        self.backend = backend_model.create(
            {'name': 'Test Shopware',
             'version': '1.7',
             'location': 'http://anyurl',
             'username': 'username',
             'warehouse_id': warehouse.id,
             'password': '42'})
        # import the base informations
        with mock_api(shopware_base_responses):
            import_batch(self.session, 'shopware.shop', self.backend.id)
            import_batch(self.session, 'shopware.shop', self.backend.id)
            import_batch(self.session, 'shopware.shop', self.backend.id)
        self.ShopwareProduct = self.env['shopware.product.product']
        self.QueueJob = self.env['queue.job']

    def test_unwrap_binding(self):
        """ Open a related action opening an unwrapped binding """
        product = self.env.ref('product.product_product_7')
        shopware_product = self.ShopwareProduct.create(
            {'openerp_id': product.id,
             'backend_id': self.backend.id})
        shopd = self._create_job(export_record, 'shopware.product.product',
                                  shopware_product.id)
        expected = {
            'name': mock.ANY,
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_id': product.id,
            'res_model': 'product.product',
        }
        self.assertEquals(shopd.open_related_action(), expected)

    def _create_job(self, func, *args):
        job = Job(func=func, args=args)
        storage = OpenERPJobStorage(self.session)
        storage.shop(job)
        shopd = self.QueueJob.search([('uuid', '=', job.uuid)])
        self.assertEqual(len(shopd), 1)
        return shopd

    def test_link(self):
        """ Open a related action opening an url on Shopware """
        self.backend.write({'admin_location': 'http://www.example.com/admin'})
        shopd = self._create_job(import_record, 'shopware.product.product',
                                  self.backend.id, 123456)
        url = 'http://www.example.com/admin/catalog_product/edit/id/123456'
        expected = {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': url,
        }
        self.assertEquals(shopd.open_related_action(), expected)

    def test_link_no_location(self):
        """ Related action opening an url, admin location is not configured """
        self.backend.write({'admin_location': False})
        self.backend.refresh()
        shopd = self._create_job(import_record, 'shopware.product.product',
                                  self.backend.id, 123456)
        with self.assertRaises(openerp.exceptions.Warning):
            shopd.open_related_action()
