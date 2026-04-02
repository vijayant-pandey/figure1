# Figure 1 Pro Backend Environment

**Requirements**

- Docker ( with docker-compose)
- AWS CLI aws-cli
- Pycharm ( Pro is nice due to docker-compose support)
- Postgres - Required for installing the python postgres database driver
- Python 3.8

Strictly speaking, pycharm isn't required, but the assumption is made throughout this documetation that that is what you
are using.

# GitHub Workflow (IMPORTANT!!!)

Please read [GitHub Workflow](docs/GITHUB_WORKFLOW.md) before working with source control. Nothing shocking or out of
the ordinary there, but want to make sure everyone is on the same page regarding commits and pull requests.

# Coding Standards

The coding standards expected for this project are described [here](docs/Standards.md)

# Introduction

This document will give you a high level overview of the Figure1 Pro backend and step you through the setup of your
development environment.

## Migrating from K8S

The previous setup ran entirely in kubernetes. In order to migrate to this setup, it will be necessary to rebuild
elasticsearch and re-import the database.

In addition, it will be necessary to add environment variables to allow for connections to the various services

1. `DB_HOST` - Set to localhost if you run the database locally
2. `DB_PORT` - The port is 5432 by default
3. `REDIS_URL` - Likely `redis://localhost:6379`
4. `ELASTICSEARCH_HOSTS` - Likely `http://localhost:9200`, but wherever your elasticsearch url is

Additionally, in order to run alembic commands, it will be necessary to set up the terminal to have the correct
pythonpath and the correct database configuration. This is set in Preferences -> Tools -> Terminal. The environment
variables should contain at least:

1. `PYTHONPATH`=`<repo_path>;`
2. `DB_HOST`=`localhost`
3. `DB_PORT`=`5432`

A similar thing can be done for the python console in order to make it usable, but it is not necessary for the
environment to work. This setup is described in detail below.

## Setting up a local environment

There are two parts to running a local environment. The first is running the support services, this includes redis,
postgres, and elasticsearch. This is handled with a docker compose file at the root called services-docker-compose. It
simply exposes the standard ports for these services on localhost. The other part is setting up the environment to talk
to these services.

### Environment Variables

When <repo_path> is referenced, it means the absolute path of this repository on your local machine. For example, this
is `/Users/colinstreicher/repos/f1-pro-backend` for me but it will be something different for everyone else. The
following environment variables are always the same in a given environment. When they are referenced elsewhere this is
what they should be set too:

1. FIRESTORE_JSON_PATH -> Set to `<repo_path>/secrets/admin.json`. This file is downloaded when you create a service
   user in google cloud. You can also download it from `firebase -> project settings -> Service accounts -> Generate new private key`
2. DB_HOST - The hostname of the database - Usually localhost
3. DB_PORT - The port of the database - Usually 5432
4. REDIS_URL - The url for the redis service - Usually redis://localhost:6379
5. ELASTICSEARCH_HOSTS - The url for elasticsearch - Usually http://localhost:9200

There are many others available, but this covers the basics.

### Support Services

The simplest approach here is too simply run docker-compose -f services-docker-compose.yaml up -d. In many cases this is
enough to ensure that everything else is configured correctly. However this can also be run via a docker-compose
deployment in pycharm which gives easy access to the logs in case that is required.

There are named volumes set up that should allow for starting and stopping of services without losing the data. There
are a couple things to be aware of however.

1. If you bring down the services with the -v option, all volumes are deleted.
2. Starting up in the ide seems to dislike or be unaware of services running outside. If you try this without renaming
   volumes, at the very least, elasticsearch will no longer be able to start without wiping the volume, though the
   databaase seems ok.

### IDE Setup

Before starting here, ensure that python3.8 is available. The directions for doing this are below.

1. Open Preferences -> Project -> Python Interpreter and click on the gear.

   1. Click Add
      1. It should default to a new VirtualEnv environment. If the venv path already exists, delete it.
      2. Pull down on the Base Interpreter menu and select python3.8
      3. Click Apply and Ok to exit
   2. Ensure the interpreter you just created is set as default.

2. If an old interpreter was deleted, then it will be necessary to reinstall the packages. When you exit, there will be
   a prompt at the top of the screen asking if you want to install the packages in the requirements.txt files. This
   should restore the packages. Alternately, once the Terminal is configured below, it can be used with the requirements
   file to reinstall the requirements.

#### Python Console

To set up the python console, go to Preferences -> Build, Execution, Deployment -> Console -> Python Console

1. Add DB_HOST, DB_PORT, and FIRESTORE_JSON_PATH to the environment variables
2. Modify the start script to the session on startup.

```python
import sys;

print('Python %s on %s' % (sys.version, sys.platform))
sys.path.extend([WORKING_DIR_AND_PYTHON_PATHS])
from figure1.core.db.database_engine import global_session

session = global_session()
```

#### Terminal

Setting up the terminal is important to ensure that alembic can be run, go to Preferences -> Tools -> Terminal

1. Set the start directory to the root of this repository
2. Set the environment variables:
   1. DB_HOST
   2. DB_PORT
   3. FIRESTORE_JSON_PATH
   4. PYTHONPATH - This should be the root of the repository, so `PYTHONPATH=<repo_path>;`

The rest of the settings here are optional

#### Flask

1. Create a new Flask run configuration
2. Choose the `Module Name` radio button
3. The target name is `figure1.run.flask_startup`
4. The Application is `initialize_debug_app`
5. Additional Options are `--host="0.0.0.0" --port=30000`
6. Flask env is development
7. FLASK_DEBUG is checked
8. Environment variables at minimum are
   1. DB_HOST
   2. DB_PORT
   3. REDIS_URL
   4. ELASTICSEARCH_HOSTS
9. Python interpreter is project default
10. Working directory is the local repository path
11. Add content roots and source roots to pythonpath

#### Celery Worker

1. Create a new python run configuration
2. Script path is `<repo_path>/venv/bin/celery`
3. Minimum parameters
   are: `worker -E --config figure1/celery_config.py -A figure1 -O fair -Q legacy_sync,celery,service,sync,backend,frontend`
4. Minimum environment variables are:
   1. DB_HOST
   2. DB_PORT
   3. REDIS_URL
   4. ELASTICSEARCH_HOSTS
   5. C_FORCE_ROOT="1"
5. Python interpreter is the default
6. Create a `celery-worker` directory under repo root. Set Working directory as `<repo_path>/celery-worker`.
7. Add content roots and source roots to pythonpath

#### Python 3.8 on mac

As of the GA release of python 3.9, it is necessary to explicitly install python 3.8 using brew as follows:

`brew install python@3.8`

Then to make it available, it is necessary to create a new link for it:

`brew link --overwrite python@3.8`

There are a couple packages that are currently incompatible with python 3.9.

# Environment Setup

## Cloning a database.

While it is possible to start with an empty database, this is not a well explored path. The recommended approach is to
clone the dev database and go from there. To do this, first clone the dev database to a local file using the database
clone script. From within the repository:

1. `bash dev/database_clone.sh dev snapshot_dev` This will connect to the dev database and clone it locally. Once it is
   finished:
2. Load the database clone locally. This uses the same script as follows `bash dev/database_clone.sh snapshot_dev local`

Check this [FAQ](https://github.com/Figure1/f1-pro-backend/blob/develop/docs/FAQ.md#i-cannot-clone-the-database) if you have issues cloning the database

## (Optional) Setting up database connectivity directly inside the PyCharm IDE

1. Open the database tab in PyCharm (all the way to the right side of the PyCharm window)
1. Click that + symbol to add a new database connection and select PostGre
1. Click 'Download Driver' if prompted
1. Once the driver has downloaded, give your new connection a name (any name will do)
1. Set the host to `localhost`
1. Set the database to `figure1`
1. Set the port to `5432`
1. Set the username to `figure1_admin`
1. Set the password to `test1234`
1. Click Apply and close the window
1. You should now see the database tables etc and perform queries directly from within PyCharm

## Adding Firebase secrets

To add secrets, create a directory at the root of the repository called secrets/ inside here, copy the admin.json file
that was downloaded from firestore when you set up your credentials. Then set the environment variable
FIRESTORE_JSON_PATH to be the full (absolute) path to that file.

Using the secrets directory is important as it is ignored by git.

In addition, ensure the following environment variables are set

- `JWT_SECRET_KEY` - Can be any arbitrary string when running locally

# Database Management with Alembic

We are using [Alembic](http://alembic.zzzcomputing.com/en/latest/index.html) to manage migration of database schemas.

If you are checking out the code for the first time you have 2 options for initializing the database. These are
equivalent operations, so run whichever makes the most sense to you:

1. Run `python -m figure1.db.figure1pro_database`, which will initialize the database tables and default data sets
   required to run the back end. However, Alembic will not know that you have a fresh database that is completely up to
   date. So after running any data initialization for the first time, _**you must**_ run `alembic stamp head` from the
   project root to tell Alembic that your database is fully up to date.
1. Run `alembic upgrade head` from the project root, which will generate the database tables and stamp Alembic to head
   automatically.

Now that you have a fresh database and Alembic's stamp is set to head, when you rebase database changes from upstream
master, you can simply run `alembic upgrade head` from the project root to automagically have your existing database (
and data) migrated to the latest schema.

If you are not checking the code out for the first time and this is the first time you're attempting to use Alembic, it
is _**highly recommented**_ that you blow your database away regenerate it using one of the methods outlined above.

If none of this Alembic mumbojumbo makes sense, head on over to their Tutorial, which I found to be very helpful:
http://alembic.zzzcomputing.com/en/latest/tutorial.html

## Creating Alembic revisions

The basic command to autogenerate an Alembic revision is `alembic revision --autogenerate -m "<comment>"`, but read
the [Alembic tutorial](http://alembic.zzzcomputing.com/en/latest/autogenerate.html#) before you start swinging that
lightsabre around - you might take someone out.

I'm not going to rehash the tutorial here, but I do want to point out that: **ALEMBIC IS NOT FIRE AND FORGET**. You have
to manually look at each autogenerated revision to make sure that it didn't miss anything. Specifically, Alembic cannot
detect views, stored procedures, and changes to table/column names. It also has varying degrees of accuracy detecting
changes of column types. Bottom line, is **test the autogenerated revision scripts before checking them into source
control**.

## Common Questions

[Frequently Asked Questions](docs/FAQ.md)
