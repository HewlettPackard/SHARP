# Makefile for GPU-based (CUDA) array incrementer

FN=$(shell basename `pwd`)
FBIN=$(shell which fission)

FISSION_ENV=cuda-src

include ../*.mk

test-%:
	make run-$(subst test-,,$(@)) to=20 args='10000000'
