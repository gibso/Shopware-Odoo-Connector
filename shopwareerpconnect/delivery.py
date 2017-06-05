# -*- coding: utf-8 -*-
##############################################################################
#
#    Authors: Guewen Baconnier, Sébastien Beau, Oliver Görtz
#    Copyright (C) 2010 BEAU Sébastien
#    Copyright 2011-2013 Camptocamp SA
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

from openerp import models, fields, api


# TODO shopware.delivery.carrier & move specific stuff
class DeliveryCarrier(models.Model):
    """ Adds Shopware specific fields to ``delivery.carrier``

    ``shopware_code``

        Code of the carrier delivery method in Shopware.
        Example: ``colissimo_express``

    ``shopware_tracking_title``

        Display name of the carrier for the tracking in Shopware.
        Example: Colissimo Express

    ``shopware_carrier_code``

        General code of the carrier, the first part of the ``shopware_code``.
        Example: ``colissimo`` for the method ``colissimo_express``.

    ``shopware_export_tracking``

        Defines if the tracking numbers should be exported to Shopware.
    """
    _inherit = "delivery.carrier"

    shopware_code = fields.Char(
        string='Shopware Carrier Code',
        required=False,
    )
    shopware_tracking_title = fields.Char(
        string='Shopware Tracking Title',
        required=False,
    )
    # in Shopware, the delivery method is something like that:
    # tntmodule2_tnt_basic
    # where the first part before the first _ is always the carrier code
    # in this example, the carrier code is tntmodule2
    shopware_carrier_code = fields.Char(
        compute='_compute_carrier_code',
        string='Shopware Base Carrier Code',
    )
    shopware_export_tracking = fields.Boolean(string='Export tracking numbers',
                                             default=True)

    @api.depends('shopware_code')
    def _compute_carrier_code(self):
        for carrier in self:
            if carrier.shopware_code:
                self.shopware_carrier_code = carrier.shopware_code.split('_')[0]
