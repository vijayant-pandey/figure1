#!/bin/bash

echo Pushing version $1 of figure1-pro-backend to DockerHub

docker build -t figure1-pro-backend:$1 .

docker tag figure1-pro-backend:$1 figure1/figure1-pro-backend:$1

docker push figure1/figure1-pro-backend:$1