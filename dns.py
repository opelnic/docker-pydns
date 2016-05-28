# Derived from work by Twisted Matrix Laboratories
# See https://twistedmatrix.com/documents/current/names/howto/custom-server.html

"""
An example demonstrating how to create a custom DNS server.
"""

from __future__ import print_function

from twisted.internet import reactor, defer
from twisted.names import client, dns, error, server
from twisted.enterprise import adbapi

import yaml
import sys
import argparse
import os


class DynamicResolver(object):
    """
    A resolver which calculates the answers to certain queries based on the
    query type and name.
    """

    def __init__(self, config, connection, logger):
        self._config     = config
        self._connection = connection
        self._logger     = logger


    def _doDynamicResponse(self, query):
        """
        Calculate the response to a query.
        """
        promise = defer.Deferred()
        name    = query.name.name
        
        # Build the record, once the query returns
        def onResult(result, authority=[], additional=[]):
            if result:
                address = result[0][0]
                self._logger("Query result: %s" % address)
                answer  = dns.RRHeader(name=name, payload=dns.Record_A(
                    address=address,
                    ttl=self._config.dns_ttl
                ))
                answers = [answer]
                promise.callback((answers, authority, additional))
            else:
                self._logger("No such domain")
                promise.errback(error.DomainError())
        
        def onError(err):
            self._logger("Query error! %s" % str(err))
            promise.errback(error.DomainError(err))

        # Run the query
        entry = self._connection.runQuery(self._config.db_query, name)
        entry.addCallbacks(onResult, onError)

        # Return the promise
        return promise


    def query(self, query, timeout=None):
        """
        Check if the query should be answered dynamically, otherwise dispatch to
        the fallback resolver.
        """
        if query.type == dns.A:
            
            # Check if domain name matches config
            labels = query.name.name.split('.')
            if ".".join(labels[1:]) == self._config.dns_domain:

                return self._doDynamicResponse(query)

        self._logger("Unexpected query %s" % query.name.name)
        return defer.fail(error.DomainError())


class Config(object):
    """
    Loads the config file
    """

    def __init__(self, path):
        try:
            with open(path, 'r') as cfg:
                data   = yaml.safe_load(cfg)
                getter = data.get
        except:
            getter = lambda key, default: default
        def top(key, default): 
            return getter(key, os.getenv(key.upper(), default))
        # Config file has preference over env var
        self.db_driver  = top('db_driver',   'MySQLdb')
        self.db_host    = top('db_host',     '127.0.0.1')
        self.db_user    = top('db_user',     'root')
        self.db_passwd  = top('db_passwd',   'Changeme')
        self.db_name    = top('db_name',     'test')
        self.db_query   = top('db_query',    'SELECT address FROM dns WHERE domain = %s')
        self.dns_ttl    = top('dns_ttl',     10)
        self.dns_domain = top('dns_domain', 'sample.org')

    def __str__(self):
        return """
        db_driver: {0.db_driver}
        db_host: {0.db_host}
        db_user: {0.db_user}
        db_password: ******
        db_name: {0.db_name}
        db_query: {0.db_query}
        dns_ttl: {0.dns_ttl}
        dns_domain: {0.dns_domain}
        """.format(self)
        

def main():
    """
    Run the server.
    """

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('-c', '--config',
        dest='config_file',
        type=str, action='store',
        default='./config.yml',
        help='Path to the configuration file'
    )
    parser.add_argument('--port', '-p',
        dest='port',
        type=int, action='store',
        default=10053,
        help='Port number for the service'
    )
    parser.add_argument('--dump', '-d',
        dest='dump_config',
        action='store_true',
        help='Dry run, just dump the values read from config file'
    )
    parser.add_argument('--verbose', '-v',
        dest='verbose',
        action='store_true',
        help='Be verbose'
    )
    params = parser.parse_args()

    # Read config file
    config = Config(params.config_file)
    if params.dump_config:
        print(config)
        sys.exit(0)
    
    # Build a connection lasting the lifetime of the service
    connection  = adbapi.ConnectionPool(
        config.db_driver,
        config.db_host,
        config.db_user,
        config.db_passwd,
        config.db_name
    )

    # Factory and protocol services
    logger   = print if params.verbose else (lambda msg: True)
    factory  = server.DNSServerFactory(clients=[
        DynamicResolver(config, connection, logger),
    ])
    protocol = dns.DNSDatagramProtocol(controller=factory)

    # Listen TCP and UDP
    reactor.listenUDP(params.port, protocol)
    reactor.listenTCP(params.port, factory)
    reactor.run()



if __name__ == '__main__':
    raise SystemExit(main())
