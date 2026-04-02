#!/bin/bash

# make sure we're using the docker-for-desktop context - otherwise you probably shouldn't be using this script
CONTEXT=$(cat ~/.kube/config | grep "current-context:" | sed "s/current-context: //")
if [ "${CONTEXT}" != "docker-for-desktop" ] && [ "${CONTEXT}" != "docker-desktop" ]; then
  echo "Slow down... switch kubectl context to 'docker-for-desktop' to avoid shooting yourself in the foot!!"
  exit
fi

# make sure we have a sym link in well-known location to the database directory in project root
db_root=/private/figure1-pg
es_root=/private/figure1-es
mg_root=/private/figure1-mongo
mg_import_root=/private/figure1-mongo-import

if [ -L "$db_root" ]; then
    echo "Removing old database symlink (requires sudo privileges)..."
    sudo rm "$db_root"
fi

if [ -L "$mg_root" ]; then
    echo "Removing old mongodb symlink (requires sudo privileges)..."
    sudo rm "$mg_root"
fi

if [ -L "$mg_import_root" ]; then
    echo "Removing old mongo import symlink (requires sudo privileges)..."
    sudo rm "$mg_import_root"
fi

if [ -L "$es_root" ]; then
    echo "Removing old elasticsearch symlink (requires sudo privileges)..."
    sudo rm "$es_root"
fi

# make sure the <project root>/database directory exists
db_dir="$PWD/database"
es_dir="$PWD/elasticsearch-ds"
old_es_dir="$PWD/elasticsearch"
mg_dir="$PWD/mongo"
mg_import_dir="$PWD/mongo-import"

if [ ! -d "$db_dir" ]; then
    echo "Creating database directory..."
    mkdir "$db_dir"
fi
if [ ! -d "$es_dir" ]; then
    if [ -d "$old_es_dir" ]; then
      echo "Found old elasticsearch directory, moving this one"
      mv "$old_es_dir" "$es_dir"
    else
      echo "Creating elasticsearch data directory"
      mkdir "$es_dir"
    fi
fi

if [ ! -d "$mg_dir" ]; then
    echo "Creating mongodb directory..."
    mkdir "$mg_dir"
fi

if [ ! -d "$mg_import_dir" ]; then
    echo "Creating mongodb import directory..."
    mkdir "$mg_import_dir"
fi

echo "Creating database symlink from $db_root --> $db_dir (requires sudo privileges)"
sudo ln -s $db_dir $db_root

echo "Creating elasticsearch symlink from $es_root --> $es_dir (requires sudo privileges)"
sudo ln -s $es_dir $es_root

echo "Creating mongodb symlink from $mg_root --> $mg_dir (requires sudo privileges)"
sudo ln -s $mg_dir $mg_root

echo "Creating mongodb import symlink from $mg_import_root --> $mg_import_dir (requires sudo privileges)"
sudo ln -s $mg_import_dir $mg_import_root

echo "Deploying application config map..."
kubectl apply -f k8s/config_maps/figure1-dev-config-maps.yaml

echo "Starting development environment..."
kubectl apply -f k8s/dev

# #echo "Deploying k8s Web UI..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v1.10.1/src/deploy/recommended/kubernetes-dashboard.yaml

echo "Dev environment running..."
