# Makefile for Python-based bounce

FN=$(shell basename `pwd`)
FBIN=$(shell which fission)

FISSION_ENV=python-src

include ../*.mk

test-%:
	make run-$(subst test-,,$(@)) to=20 args="A short message"
