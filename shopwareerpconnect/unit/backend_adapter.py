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

import socket
import logging
import xmlrpclib
from shopware_rest import rest as shopwarelib

from openerp.addons.connector.unit.backend_adapter import CRUDAdapter
from openerp.addons.connector.exception import (NetworkRetryableError,
                                                RetryableJobError)
from datetime import datetime
_logger = logging.getLogger(__name__)


MAGENTO_DATETIME_FORMAT = '%Y/%m/%d %H:%M:%S'


recorder = {}


def call_to_key(method, arguments):
    """ Used to 'freeze' the method and arguments of a call to Shopware
    so they can be hashable; they will be shopd in a dict.

    Used in both the recorder and the tests.
    """
    def freeze(arg):
        if isinstance(arg, dict):
            items = dict((key, freeze(value)) for key, value
                         in arg.iteritems())
            return frozenset(items.iteritems())
        elif isinstance(arg, list):
            return tuple([freeze(item) for item in arg])
        else:
            return arg

    new_args = []
    for arg in arguments:
        new_args.append(freeze(arg))
    return (method, tuple(new_args))


def record(method, arguments, result):
    """ Utility function which can be used to record test data
    during synchronisations. Call it from ShopwareCRUDAdapter._call

    Then ``output_recorder`` can be used to write the data recorded
    to a file.
    """
    recorder[call_to_key(method, arguments)] = result


def output_recorder(filename):
    import pprint
    with open(filename, 'w') as f:
        pprint.pprint(recorder, f)
    _logger.debug('recorder written to file %s', filename)


class ShopwareLocation(object):

    def __init__(self, location, username, token):
        self.username = username
        self.token = token

        if not location.endswith('/'):
            location += '/'
        self._location = location + 'api/'

    @property
    def location(self):
        location = self._location
        return location


class ShopwareCRUDAdapter(CRUDAdapter):
    """ External Records Adapter for Shopware """

    def __init__(self, connector_env):
        """

        :param connector_env: current environment (backend, session, ...)
        :type connector_env: :class:`connector.connector.ConnectorEnvironment`
        """
        super(ShopwareCRUDAdapter, self).__init__(connector_env)
        backend = self.backend_record
        shopware = ShopwareLocation(
            backend.location,
            backend.username,
            backend.token)
        self.shopware = shopware

    def search(self, filters=None):
        """ Search records according to some criterias
        and returns a list of ids """
        raise NotImplementedError

    def read(self, id, attributes=None):
        """ Returns the information of a record """
        raise NotImplementedError

    def search_read(self, filters=None):
        """ Search records according to some criterias
        and returns their information"""
        raise NotImplementedError

    def create(self, data):
        """ Create a record on the external system """
        raise NotImplementedError

    def write(self, id, data):
        """ Update records on the external system """
        raise NotImplementedError

    def delete(self, id):
        """ Delete a record on the external system """
        raise NotImplementedError

    def _call(self, resource, arguments, method='GET'):
        try:
            _logger.debug("Start calling Shopware api %s", method)
            client = shopwarelib.sapi()
            client.setCredentials(self.shopware.username,
                                  self.shopware.token,
                                  self.shopware.location)
            result = client.call(resource, method, arguments, arguments)

            if type(result) is type(bool) and result is False:
                raise NetworkRetryableError(
                    'Shopware API could not be reached.'
                )

            return result
        except (socket.gaierror, socket.error, socket.timeout) as err:
            raise NetworkRetryableError(
                'A network error caused the failure of the job: '
                '%s' % err)
        except xmlrpclib.ProtocolError as err:
            if err.errcode in [502,   # Bad gateway
                               503,   # Service unavailable
                               504]:  # Gateway timeout
                raise RetryableJobError(
                    'A protocol error caused the failure of the job:\n'
                    'URL: %s\n'
                    'HTTP/HTTPS headers: %s\n'
                    'Error code: %d\n'
                    'Error message: %s\n' %
                    (err.url, err.headers, err.errcode, err.errmsg))
            else:
                raise


class GenericAdapter(ShopwareCRUDAdapter):

    _model_name = None
    _shopware_model = None

    def search(self, filters=None):
        """ Search records according to some criterias
        and returns a list of ids

        :rtype: list
        """
        return self._call('%sSearch' % self._shopware_model,
                          {'filter': filters} if filters else {})

    def read(self, id, attributes=None):
        """ Returns the information of a record

        :rtype: dict
        """
        return self._call('%s' % self._shopware_model + '/' + str(id),
                          {'attributes' : attributes})

    def search_read(self, filters=None):
        """ Search records according to some criterias
        and returns their information"""
        return self._call('%s.list' % self._shopware_model, [filters])

    def create(self, data):
        """ Create a record on the external system """
        return self._call('%s.create' % self._shopware_model, [data])

    def write(self, id, data):
        """ Update records on the external system """
        return self._call('%s.update' % self._shopware_model,
                          [int(id), data])

    def delete(self, id):
        """ Delete a record on the external system """
        return self._call('%s.delete' % self._shopware_model, [int(id)])
