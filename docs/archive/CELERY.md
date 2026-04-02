## Celery

The official documentation on Celery is extensive and quite easy to navigate and should be used for reference. The 
documentation can be found at http://docs.celeryproject.org/en/latest/userguide/index.html

## Creating a task

Tasks are defined as decorated functions, the celery decorator can take a number of arguments that define the behaviour
of a task in the queue, however none are mandatory for simple tasks.

```
from celery import Celery
from figure1 import celery_config 

celery = Celery(__name__)
celery.config_from_object(celery_config)

@celery.task(serializer='pickle', retry_backoff=300, retry_backoff_max=1800, autoretry_for=(RateLimitError,), rate_limit='10/m')
def get_mesh_data(case, url):
...

```

To call this task, import the name of the function( get_mesh_data in this case ) and call it with either apply_async() 
or delay(). Both have the same result, however, calling delay is simpler at the cost of not supporting as many options.
Documentation is here on available options http://docs.celeryproject.org/en/latest/userguide/calling.html
```
# delay
get_mesh_data.delay(case=case, url=self.url)

# apply_async
get_mesh_data.apply_async(kwargs={'case'=case,'url'=self.url})
```

Once either of these are called, the task is sent to the queue. There is a celery option that can be set in the 
configuration called task_always_eager. Setting this to true allows the same process to execute it without having to
start a worker.

## Worker Management

The workers in celery are run from the same codebase, that is, they have access to all the same code and the process that
sent the task. 

### Starting a worker

To start a worker, simply execute `celery worker --app <path to module>`. The app path must point to a module with a 
celery app instance exposed. In figure1.tagging for example, we import celery from tasks, so from the base directory 
( in the docker container, /usr/src/app ), we can run `celery worker --app figure1.tagging`. 

To configure a pycharm runner for a celery worker, edit run/debug configurations and create a new Python configuration.
The settings are:

Script Path: `/usr/local/bin/celery`

Parameters:  `worker -E -A figure1.tagging --workdir /usr/src/app --broker redis://redis:6379/5 -c 1 --loglevel debug`

Environment: `PYTHONUNBUFFERED=1;C_FORCE_ROOT=“1”`

Working Directory: `/usr/local/bin`

### Stopping a worker

When a worker is started, it prefetches a number of jobs to avoid hitting the queue when a new task is needed. When the 
worker stops, it unacknowledges these tasks and pushes them back to the queue.

### Purging the queue

Sometimes the queue may end up having things that you want to flush, in this case, first stop any workers running so the
tasks are sent back to the queue. Then, when the worker is started, add --discard to the command to start the worker, so
`worker -E -A figure1.tagging --workdir /usr/src/app --broker redis://redis:6379/5 -c 1 --loglevel debug --discard` this 
will flush all the messages in the queue before starting. 

## Brokers

Celery currently uses redis as a broker, so lists are used instead of queues, though they behave in the same way for the
most part. There are some small changes in terms of how priority are managed, however this is not something we are using
right now. 

## Priority

Tasks can be given a priority which determines how urgently a task is processed. We are not using priority currently,
if/when we start using it, our usage will be documented here.

## Flower

Flower is a web-based UI that is used for introspection into the workers. It can be used to revoke tasks, change the 
queues a worker listens too, or to restart workers. 
It is helpful to get a visual indication of what is going on, and to send commands to the workers. It works by sending 
remote control commands through the queues to the workers. Workers do not pre-empt tasks to pick up anything from the
queue, so a remote control command may not be executed immediately. 
In the local dev environment, flower is accessed by going to http://localhost:30055.
