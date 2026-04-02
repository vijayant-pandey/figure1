#!/bin/bash

# make sure we're using the docker-for-desktop context - otherwise you probably shouldn't be using this script
CONTEXT=$(cat ~/.kube/config | grep "current-context:" | sed "s/current-context: //")

if [ "${CONTEXT}" != "docker-for-desktop" ] && [ "${CONTEXT}" != "docker-desktop" ]; then
  echo "Slow down... switch kubectl context to 'docker-for-desktop' to avoid shooting yourself in the foot!!"
  exit
fi

echo "Stopping development environment..."
kubectl delete -f k8s/dev/
