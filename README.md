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

The server connects to a database and expects request in ports 10053 TCP and UDP. When it receives an A query (and only an A query), in a given domain, it searches for the name in the database and returns the IP address (a single IP address).

The configuration parameters for connection to the database can be given as environment variables:

  - **DB_DRIVER**: the DB-API driver, currently only MySQLdb packed in the container image.
  - **DB_HOST**: the database server hostname (and port)
  - **DB_USER**: the database username
  - **DB_PASSWD**: the database password
  - **DB_NAME**: The database name
  - **DB_QUERY**: The query to perform to resolve the name. By default, *"SELECT address FROM dns WHERE query = %s"*
  - **DNS_TTL**: The TTL of A records
  - **DNS_DOMAIN**: The subdomain for which the server is authoritative

These variables can also be provided in a configuration file in YAML format mounted in **/usr/src/app/config.yml**, like the following:

```
---
db_driver:  "MySQLdb"
db_host:    "mysqldb"
db_user:    "root"
db_passwd:  "Changeme"
db_name:    "test"
db_query:   "SELECT address FROM dns WHERE domain = %s"
dns_ttl:    3600
dns_domain: "example.org"
```

For example, if you want to be authoritative for a domain "remote.demo.com", create a table "dns" in your mysql server such as:

```
CREATE TABLE dns (
	'domain'  VARCHAR(255) NOT NULL PRIMARY KEY,
	'address' VARCHAR(16) NOT NULL
);

INSERT INTO dns VALUES ('test.remote.demo.com', '1.2.3.4')
```

Then insert your records there, and query them:

```
dig @container_ip -p 10054 test.remote.demo.com
```
