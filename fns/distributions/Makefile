# Makefile for synthetic distributions

FN=$(shell basename `pwd`)
FBIN=$(shell which fission)

FISSION_ENV=distributions-src

include ../*.mk

test-%:
	make run-$(subst test-,,$(@)) to=20 args='{\"method\": \"lognormal\"}'
