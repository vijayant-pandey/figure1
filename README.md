# Services API
These instructions allow you to run the Services API locally. If you run the optional steps, you'll have the full F1 tech stack running locally with the exception of the PostgresSQL database.

## Open an SSH Tunnel to the PostgresSQL database
The command structure is as follows to open up an SSH tunnel to the PostgresSQL Database hosted on GCP. Update the `compute_instance_zone`, `compute_instance_name`, `gcp project name`, and `ip_address` to the appropriate values.
```
gcloud compute ssh --zone "compute_instance_zone" "compute_instance_name" --project "gcp project name" --ssh-flag="-L 5432:ip_address:5432" --tunner-though-iap
```
Below is the same command that opens an SSH tunnel to the f1-development project. 
```
gcloud compute ssh --zone "us-central1-f" "srv-f1-dev-utility-box-us-central1" --project "f1-development" --ssh-flag="-L 5432:10.209.1.3:5432"  --tunnel-through-iap
```

## Setup local .env file
Create .env file (if you already dont have it) and add LOCAL_BUILD=false on top of the file. 
* Run `sh generate-local-env.sh`. This will generate .env.runtime, copy the contents to your .env file.
* Update your `CELERY_BROKER_URL`, `REDIS_URL`, and `DB_HOST` environment variables to the following:
```
DB_HOST=host.docker.internal
CELERY_BROKER_URL=redis://redis:6379
REDIS_URL=redis://redis:6379
```

## Use Docker Compose to build individual images
Use thhe Docker Compose file included in the repository to build the Redis, Services, and Celery images. 
```
docker compose -f docker-compose.yaml up -d
```

After making changes to the Services API codebase, run the following command to rebuild the images.
```
docker compose -f docker-compose.yaml build --no-cache figure1 celery flower
```
The run the following to use the new images.
```
docker compose -f docker-compose.yaml up -d --force-recreate figure1 celery flower
```


## Use Docker Compose to build individual images (secure)
call the ./docker-compose-secure.sh script as a wrapper for docker commands that uses docker-compose.local.yaml to pull .env.runtime into RAM instead of writing a .env to the filesystem, the command follows the format `./docker-compose-secure.sh {flags}`
The steps in the above section can be run with 
```
./docker-compose-secure.sh up -d

./docker-compose-secure.sh build --no-cache figure1 celery flower

./docker-compose-secure.sh up -d --force-recreate figure1 celery flower
```

## Optional steps
Connect local functions_v2
* Go to /utils/requestUtils.js in your functions folder and update backend_host to `http://127.0.0.1:30000`. This will connect your firebase functions to local services (works only when running emulator)
* Configure your local web repository to connect to the local functions.


