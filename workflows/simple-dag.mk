id := demo
name := Example workflow
description := A demonstration of a simple workflow with dependencies
version := 1.0
specVersion := 0.8
start := CreateInputFiles
end := swapbytes-2.csv

basedir := /home/frachten/sharp
outdir := $(basedir)/runlogs/demo
launcher := $(basedir)/launchers/launch.py --description "$(description)"
csv_files := swapbytes-1.csv inc.csv cuda-inc.csv swapbytes-2.csv


.PHONY: clean CreateInputFiles inc-both sleepy

all:
	mkdir -p $(outdir)
	cd $(outdir); make -f $(abspath $(lastword $(MAKEFILE_LIST))) demo.pdf

demo.pdf: $(end)
	@echo compiling final report in `pwd`...

clean:
	rm -rf demo.pdf $(csv_files)

CreateInputFiles: 
	head -c 10m /dev/zero > /tmp/zeros-10m &
	head -c 100m /dev/zero > /tmp/zeros-100m &
	wait

swapbytes-1.csv: CreateInputFiles
	$(launcher) --mpl 10 --timeout 10 -e $(id) -p local swapbytes /tmp/zeros-10m

inc-both: swapbytes-1.csv

inc.csv: inc-both
	$(launcher) --mpl 15 --timeout 30 -e $(id) -p fission inc 100000

cuda-inc.csv: inc-both
	$(launcher) --mpl 5 --timeout 30 -e $(id) -p fission cuda-inc 100000

sleepy: inc.csv cuda-inc.csv
	sleep 10

swapbytes-2.csv: sleepy
	$(launcher) --mpl 10 --timeout 20 -e $(id) -p local swapbytes /tmp/zeros-100m
