# Workflow for a benchmark measuring different start-up latencies for backend

# Specific variables for this benchmark:
task := start
csv_files := $(task).csv
repeats := 100

# Standard variables describing this benchmarks:

mypath := $(abspath $(lastword $(MAKEFILE_LIST)))
id := $(shell basename $(dir $(mypath)))
description := Measures the latency of alternately launching cold, warm, and local no-op function
backend := fission
version := 1.0
outputs = $(foreach csv,$(csv_files),$(outdir)/$(csv))

.PHONY: all outputs

all: csv
	cp -u ../common.R * $(outdir)
	cd $(outdir); make -f $(mypath) $(id).pdf

csv: Makefile
	$(MAKE) -j outputs
	@touch csv

outputs:
	# Run the first pair separately because it's not in append mode:
		$(launcher) --timeout 300 -e $(id) -t $(task) -c -r 1 -b $(backend) nope
		$(launcher) --timeout 10 -e $(id) -t $(task) -a -r 1 -b $(backend) nope
		$(launcher) --timeout 10 -e $(id) -t $(task) -a -r 1 -b local nope
	for i in $(shell seq 1 $(shell expr $(repeats) - 1)) ;\
	do \
		$(launcher) --timeout 300 -e $(id) -t $(task) -a -c -r 1 -b $(backend) nope; \
		$(launcher) --timeout 10 -e $(id) -t $(task) -a    -r 1 -b $(backend) nope; \
		$(launcher) --timeout 10 -e $(id) -t $(task) -a -r 1 -b local nope; \
	done


include $(shell dirname $(mypath))/../common.mk  # Needs to be last thing in file
