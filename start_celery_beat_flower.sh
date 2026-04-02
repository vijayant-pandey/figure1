#!/bin/sh

# Start Celery Beat in the background
celery -A figure1 beat &

# Start Celery Flower
celery -A figure1 flower &

wait