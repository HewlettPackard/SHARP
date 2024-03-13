# Makefile for rodinia-omp functions

FN=$(shell basename `pwd`)
FBIN=$(shell which fission)

FISSION_ENV=rodinia-src

include ../*.mk

test-%:
	make run-$(subst test-,,$(@)) to=20 args='backprop'
