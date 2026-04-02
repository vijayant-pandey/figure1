#!/bin/bash

if [ ! -f .gitignore ] ; then
    echo "Run me from the repository root please"
    exit 1
fi

echo "Building mongo docker image"
docker build -f dev/mongo-dockerfile -t figure1-mongo:dev dev/

echo "Building base development docker image..."
#docker build --build-arg git_user_name="${1}" --build-arg git_access_token="${2}" -t figure1-pro-backend:dev-base .
docker build -t figure1-pro-backend:dev-base .

echo "Make sure we have ssh keys for debug docker image..."
mkdir -p ssh_keys # add to .gitignore!!
if [ ! -f ssh_keys/docker ] ; then
    echo "generating key"
    rm -f ssh_keys/docker*
    ssh-keygen -t rsa -f ssh_keys/docker -N "" -m PEM
else
    echo "using existing key"
fi

# unfortunately docker native doesn't mount in /Applications, either change that or do this
echo "Gather latest pycharm_helper files so that we can connect PyCharm's debugger to the docker container..."
rm -rf ~/.pycharm_helpers
cp -R /Applications/PyCharm.app/Contents/helpers/ ~/.pycharm_helpers

echo "Building debug docker image..."
docker build -f dev/Dockerfile \
     --build-arg AUTH_KEY="$(cat ssh_keys/docker.pub)" \
     -t figure1-pro-backend_debug .

echo "Success: use dev/start-dev.sh and dev/stop-dev.sh to control the container."
