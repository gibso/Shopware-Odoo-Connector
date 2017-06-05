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


class ShopwareConfigSettings(models.TransientModel):
    _inherit = 'connector.config.settings'

    module_shopwareerpconnect_pricing = fields.Boolean(
        string="Prices are managed in OpenERP with pricelists",
        help="Prices are set in OpenERP and exported to Shopware.\n\n"
             "This installs the module shopwareerpconnect_pricing.",
    )
    module_shopwareerpconnect_export_partner = fields.Boolean(
        string="Export Partners to Shopware (experimental)",
        help="This installs the module shopwareerpconnect_export_partner.",
    )
