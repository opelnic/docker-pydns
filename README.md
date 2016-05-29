Small python DNS server
-----------------------

This is a really small DNS server implemented in python, based on [twisted](https://twistedmatrix.com/trac/), and with a SQL backend. It is intended to be used as a simple resolver for nginx, no more no less.

To build the container:

```
git clone https://github.com/rjrivero/docker-pydns.git

cd docker-pydns
docker build --rm -t pydns .
```

Configuration
-------------

The server connects to a database and expects request in ports 10053 TCP and UDP. When it receives an A query (A, AAAA, A6) in a given domain, it searches for the name in the database and returns the IP address (a single IP address).

The configuration parameters can be given as environment variables:

  - **DB_DRIVER**: the DB-API driver, currently only *MySQLdb* packed in the container image.
  - **DB_HOST**: the database server hostname
  - **DB_PORT**: the database server TCP port (defaults to 3306)
  - **DB_USER**: the database username
  - **DB_PASSWD**: the database password
  - **DB_NAME**: The database name
  - **DB_QUERY**: The query to perform to resolve the name. By default, *"SELECT address FROM dns WHERE domain = %s"*
  - **DNS_TTL**: The TTL of A records
  - **DNS_HOSTS**: Path to the hosts file, defaults to */etc/hosts*
  - **DNS_DOMAIN**: The domain for which the server is authoritative

These variables can also be provided in a configuration file in YAML format mounted at **/usr/src/app/config.yml**, like the following:

```
---
db_driver:   "MySQLdb"
db_host:     "mysqldb"
db_port:      3306
db_user:     "root"
db_passwd:   "Changeme"
db_name:     "test"
db_query:    "SELECT address FROM dns WHERE domain = %s"
dns_ttl:      3600
dns_hosts:   "/etc/hosts"
dns_domains:
  - "example.org"
  - "remote.demo.com"
```

As shown above, the configuration file method allows you to specificy several DNS domains, instead of only one. **Beware!** the environment parameter is **DNS_DOMAIN** (singular), while the config file parameter is **dns_domains** (plural)!

Usage
------

First, create a table "dns" in your mysql server, such as:

```
CREATE TABLE dns (
	'domain'  VARCHAR(255) NOT NULL PRIMARY KEY,
	'address' VARCHAR(16) NOT NULL
);
```

Then insert your records:

```
INSERT INTO dns VALUES ('test.demo.com', '1.2.3.4');

# You can be recursive if you want, too
INSERT INTO dns VALUES ('recursive.demo.com', 'www.google.es');
```

Then, run your server pointing to that table:

```
docker run --rm --name pydns \
    -e DB_HOST=<your mysql server IP> \
    -e DB_PORT=3306 \
    -e DB_USER=<your user> \
    -e DB_PASSWD=<your passwd> \
    -e DB_NAME=<the database name> \
    -e DB_SQL="SELECT address FROM dns WHERE domain = %s" \
    -e DNS_TTL=600 \
    -e DNS_DOMAIN=demo.com \
    -e DNS_HOSTS=/etc/hosts \
    -p 10053:10053 \
    -p 10053:10053/udp \
    pydns
```

That is all, test it!

```
dig @127.0.0.1 -p 10053 test.demo.com
dig @127.0.0.1 -p 10053 recursive.demo.com
```
