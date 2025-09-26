# Makefile for Llama2 inference

FN=$(shell basename `pwd`)
FBIN=$(shell which fission)

FISSION_ENV=ollama

include ../*.mk

test-%:
	make run-$(subst test-,,$(@)) to=20 args='Who are you'
