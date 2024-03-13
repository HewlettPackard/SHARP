# Makefile for single-function MPI

FN=$(shell basename `pwd`)
FBIN=$(shell which fission)

FISSION_ENV=mpi-single-src

include ../*.mk

test-%:
	make run-$(subst test-,,$(@)) to=20 args='4'
