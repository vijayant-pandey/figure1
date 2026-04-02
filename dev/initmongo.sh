#!/bin/bash
set -ex

/mongodb-linux-x86_64-3.0.15/bin/mongod --syslog --fork --storageEngine wiredTiger --dbpath /data/mongo

/mongodb-linux-x86_64-3.0.15/bin/mongorestore --drop --db figure1 --dir /data/restore
