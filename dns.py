# Derived from work by Twisted Matrix Laboratories
# See https://twistedmatrix.com/documents/current/names/howto/custom-server.html

"""
An example demonstrating how to create a custom DNS server.
"""

from twisted.internet import reactor, defer
from twisted.names import client, dns, error, server, hosts, cache
from twisted.python import log
from twisted.logger import Logger, textFileLogObserver
from twisted.enterprise import adbapi

import yaml
import sys
import argparse
import os
import ipaddress

from textwrap import dedent



class DynamicResolver(object):
    """
    A resolver which calculates the answers to certain queries based on the
    query type and name.
    """

    def __init__(self, config, connection, resolver, logger):
        """
        Build the resolver.
        
        @param config: the configuration object.
        @param connection: a database connection object.
        @param resolver: global DNS resolver
        """
        self._config     = config
        self._connection = connection
        self._resolver   = resolver
        self._logger     = logger


    def _doCreateRecord(self, query, name, representation):
        """
        Converts the string representation of an IP address to a
        RR Record.
        
        Raises ValueError if representation is not an address,
        but a domain name.
        
        Raises TypeError if representation is an address, but the
        IP version of the query and the address mismatch
        (e.g. queried for an A record but got IPv6 instead)
        """
        # ip_address requires unicode strings
        if sys.version_info <= (3, 0) and not isinstance(representation, unicode):
            representation = representation.decode('utf8')
        address     = ipaddress.ip_address(representation)
        record_type = None
        # Try to match the record to the representation
        if address.version == 4:
            if query.type == dns.A:
                record_type = dns.Record_A
        else:
            if query.type == dns.AAAA:
                record_type = dns.Record_AAAA
            elif query.type == dns.A6:
                record_type = dns.Record_A6
        # If we couldn't match, raise an Error
        if record_type is None:
            raise TypeError("Mismatched query and address")
        return dns.RRHeader(
            name=name,
            payload=record_type(address=str(address)),
            ttl=self._config.dns_ttl
        )


    def _doDynamicResponse(self, query):
        """
        Calculate the response to a query.
        """
        promise = defer.Deferred()
        name    = query.name.name

        # Get the info from the database and resolve it
        def onResult(result, answers=[], additional=[]):
            if not result:
                self._logger.info("{data}: No such domain", data=name)
                promise.errback(error.DomainError())
                return
            # First, try to translate the value to an IP address
            representation = result[0][0]
            self._logger.debug("SQL query result: {data}" ,
                data=representation)
            try:
                record = self._doCreateRecord(query, name, representation)
                promise.callback((answers, [record,], additional))
            # If not an IP address, resolve it recursively
            except ValueError:
                query.name.name = representation
                self._logger.warn("Recursively resolve domain: {data}",
                    data=representation)
                entry = self._resolver.query(query, timeout=(3,3,3))
                entry.chainDeferred(promise)
            # If mistmatched query and address, return error
            except TypeError as err:
                self._logger.failure("Mismatched address and query")
                promise.errback(error.DomainError())
            
        # Error handler, propagates the error back
        def onError(err):
            self._logger.failure("SQL query failed", failure=err)
            promise.errback(err)

        # Run the query
        entry = self._connection.runQuery(self._config.db_query, [name])
        entry.addCallbacks(onResult, onError)

        # Return the promise
        return promise


    def query(self, query, timeout=None):
        """
        Check if the query should be answered dynamically, otherwise dispatch to
        the fallback resolver.
        """
        if query.type in (dns.A, dns.AAAA, dns.A6):
            
            # Check if domain name matches config
            labels = query.name.name.split('.')
            if ".".join(labels[1:]) in self._config.dns_domains:

                return self._doDynamicResponse(query)

        self._logger.info("Unsupported query: {data}", data=query)
        return defer.fail(error.DomainError())


class Config(object):
    """
    Loads the config file
    """

    def __init__(self, path, logger):
        try:
            with open(path, 'r') as cfg:
                data   = yaml.safe_load(cfg)
                getter = data.get
        except Exception as err:
            logger.failure("Error loading config file", failure=err)
            getter = lambda key, default: default
        def top(key, default): 
            # Environment variables have preference over config file
            return os.getenv(key.upper(), getter(key, default))
        self.db_driver   = top('db_driver',   'MySQLdb')
        self.db_host     = top('db_host',     '127.0.0.1')
        self.db_port     = int(top('db_port',  3306))
        self.db_user     = top('db_user',     'root')
        self.db_passwd   = top('db_passwd',   'Changeme')
        self.db_name     = top('db_name',     'test')
        self.db_query    = top('db_query',    'SELECT address FROM dns WHERE domain = %s')
        self.dns_ttl     = int(top('dns_ttl',  300))
        self.dns_hosts   = top('dns_hosts',   '/etc/hosts')
        # dns_domains is special because the environment variable
        # name does not match the config variable name (environment
        # only allows for one domain)
        self.dns_domains = os.getenv("DNS_DOMAIN", 
            getter('dns_domains', 'example.org'))
        # Turn the domain entry / list into a dict
        try:
            # Python 2
            if isinstance(self.dns_domains, basestring):
                self.dns_domains = [self.dns_domains,]
        except NameError:
            # Python 3
            if isinstance(self.dns_domains, str):
                self.dns_domains = [self.dns_domains,]
        domains = dict()
        for item in self.dns_domains:
            domains[item] = True
        self.dns_domains = domains


    def __str__(self):
        return dedent("""
        db_driver:   "{0.db_driver}"
        db_host:     "{0.db_host}"
        db_port:     "{0.db_port}"
        db_user:     "{0.db_user}"
        db_password: ******
        db_name:     "{0.db_name}"
        db_query:    "{0.db_query}"
        dns_ttl:      {0.dns_ttl}
        dns_hosts:   "{0.dns_hosts}"
        dns_domains:
        {1}
        """).format(self, "\n".join("  - \"%s\"" % domain
                          for domain in self.dns_domains))



def main():
    """
    Run the server.
    """

    parser = argparse.ArgumentParser(
        description='Resolve DNS queries from Database')
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
    parser.add_argument('--dry-run', '-d',
        dest='dry_run',
        action='store_true',
        help='Dry run, just check the config file'
    )
    #parser.add_argument('--verbose', '-v',
    #    dest='verbose',
    #    action='store_true',
    #    help='Be verbose'
    #)
    params = parser.parse_args()

    # Log to stdout, as this is intended to run in docker
    log.startLogging(sys.stdout)
    # Make new logging style compatible to traditional one
    def observer(event, log=log):
        log.msg(event['log_format'].format(**event))
        if 'log_failure' in event:
            log.err(event['log_failure'])
    logger = Logger(namespace='default', observer=observer)

    # Read config file
    config = Config(params.config_file, logger)
    logger.debug("Running with the following parameters:\n{data}", data=config)

    # Dry run
    if params.dry_run:
        sys.exit(0)
    
    # Build a connection lasting the lifetime of the service
    connection = adbapi.ConnectionPool(
        config.db_driver,
        host=config.db_host,
        port=config.db_port,
        user=config.db_user,
        passwd=config.db_passwd,
        db=config.db_name
    )

    # Build a global Resolver lasting the lifetime of the service
    resolver = client.createResolver()

    # Factory and protocol services
    factory  = server.DNSServerFactory(
        caches=[
            cache.CacheResolver(),
        ],
        # Use "clients" instead of "authorities", so caching works
        clients=[
            hosts.Resolver(file=config.dns_hosts, ttl=config.dns_ttl),
            DynamicResolver(config, connection, resolver, logger),
        ]
    )
    protocol = dns.DNSDatagramProtocol(controller=factory)

    # Listen TCP and UDP
    reactor.listenUDP(params.port, protocol)
    reactor.listenTCP(params.port, factory)
    reactor.run()



if __name__ == '__main__':
    raise SystemExit(main())
