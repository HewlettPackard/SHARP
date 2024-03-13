# Workflow for a benchmark showing how the backend handles increasing parallelism

# Specific variables for this benchmark:
task := psleep
csv_files := $(task).csv
repeats := 100

# Standard variables describing this benchmarks:

mypath := $(abspath $(lastword $(MAKEFILE_LIST)))
id := $(shell basename $(dir $(mypath)))
description := Measures the latency of alternately launching cold, warm, and local no-op function
backend := fission
version := 1.0
outputs = $(foreach csv,$(csv_files),$(outdir)/$(csv))

# Specific variables for this benchmark:
max_mpl := 10

.PHONY: all outputs

all: csv
	cp -u ../common.R * $(outdir)
	cd $(outdir); make -f $(mypath) $(id).pdf

csv: Makefile
	$(MAKE) -j outputs
	@touch csv

outputs:
	# Start with a cold run to reset the backend
		$(launcher) --timeout 300 -e $(id) -t $(task) -c  -b $(backend) sleep 1
	# Run with MPL one to recreate the file:
		$(launcher) --timeout 10 -e $(id) -t $(task) --mpl 1 -b $(backend) sleep 1
	# Now loop over increasing values of mpl:
	for mpl in $(shell seq 2 $(max_mpl)); \
	do \
		$(launcher) --timeout 10 -e $(id) -t $(task) --mpl $$mpl -b $(backend) -a sleep 1; \
	done


include $(shell dirname $(mypath))/../common.mk  # Needs to be last thing in file
