# Makefile for numpy-based matrix multiplication

FN=$(shell basename `pwd`)
FBIN=$(shell which fission)

FISSION_ENV=python-src

include ../*.mk

test-%:
	make run-$(subst test-,,$(@)) to=20 args='100'
