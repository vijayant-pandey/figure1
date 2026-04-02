#!/usr/bin/env bash

if [ "$#" -ne 2 ]; then
    echo "usage:"
    echo
    echo "db-secret-gen.sh <username> <password>"
    exit
fi

echo "Updating k8s secret for d20.db credentials..."

kubectl create secret generic figure1.db \
    --from-literal=USERNAME="${1}" \
    --from-literal=PASSWORD="${2}" \
    -o yaml --dry-run | kubectl apply -f -
