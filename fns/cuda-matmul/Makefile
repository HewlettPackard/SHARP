# Makefile for GPU-based (CUDA) matrix multiplier

FN=$(shell basename `pwd`)
FBIN=$(shell which fission)

FISSION_ENV=cuda-src

include ../*.mk

# Override prep-docker to include GPU access
prep-docker:
	make clean-docker
	make prep-docker-image
	docker run -d --rm --gpus all --name ${FN} ${DOCKER_ENV}

test-%:
	make run-$(subst test-,,$(@)) to=20 args='1000'
