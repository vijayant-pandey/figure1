#!/bin/bash
export COMPOSE_PROJECT_NAME="test_environment"

docker-compose -f docker-compose-test.yaml down -v

echo "Building docker test image"
docker-compose -f docker-compose-test.yaml build
echo "Code Style"
docker-compose -f docker-compose-test.yaml run --rm figure1 pycodestyle figure1/
echo "Executing tests"
docker-compose -f docker-compose-test.yaml run --rm figure1 python -m pytest figure1/tests  -vvvv --showlocals -x

docker-compose -f docker-compose-test.yaml down -v