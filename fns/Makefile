# Makefile for all compound functions.
# Use "make all" to build/compile the functions code and inputs, as necessary.
# Use "make prep-X" to install the functions in framework X (e.g., "prep-fission")
# Use "make X-clean" to uninstall functions from framework X.

# Update the variable below to avoid its prompt at every run
export IMAGE_REPO ?=$(shell read -p "Enter the Docker registry (e.g., your_registry/your_repo): " input && echo $$input)

# Which functions to build all subdirectories):
FNS_DEFAULT=$(wildcard */)

FNS ?= $(FNS_DEFAULT)

.PHONY: all

all:
	for fn in ${FNS}; do make -j -C $${fn} prep-fission; done
	for fn in ${FNS}; do make -j -C $${fn} prep-knative; done
prep-%:
	for fn in ${FNS}; do make -C $${fn} $@; done

test-%:
	for fn in ${FNS}; do make -C $${fn} $@; done

clean-%:
	for fn in ${FNS}; do make -C $${fn} $@; done
