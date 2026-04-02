#!/bin/bash
set -e

docker buildx build \
  --platform=linux/amd64 \
  -t us-central1-docker.pkg.dev/f1-migration-sb/figure1-app-images/f1-services:latest \
  . 