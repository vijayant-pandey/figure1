#!/usr/bin/env bash

if [ "$#" -ne 1 ]; then
    echo "usage:"
    echo
    echo "rest-jwt-secret-gen.sh secret_key"
    exit
fi

echo "Updating k8s secret for rest.jwt_secret_key..."

kubectl create secret generic figure1.rest-endpoints \
    --from-literal=REST_JWT_SECRET_KEY="${1}" \
    -o yaml --dry-run | kubectl apply -f -
