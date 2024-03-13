# Makefile to build reports from one or more benchmarks
# Reports are stored in ../reports, under a subdirectory for each report
#

benchmarks := $(foreach dir,$(wildcard */),$(shell basename $(dir)))
experiment := misc
backend := local
formats = pdf_book html_document word_document2 powerpoint_presentation

basedir := $(shell dirname $(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
report_dir := $(basedir)/reports/"$(experiment)-$(backend)"
report_files = $(foreach b,$(benchmarks),$(b).Rmd,)
local_id = $(shell id -u):$(shell id -g)
env_file := $(report_dir)/environment
reporter_image := eitanf/reporter:1.0  # Replace with your local image if you have one

rcode = setwd(\"$(report_dir)\"); library(\"bookdown\"); bookdown::render_book(\"report.Rmd\", \"bookdown::$(format)\", config_file=\"report.yml\")
Rcmd=/usr/bin/env R -e \
		"setwd(\"$(report_dir)\"); \
		library(\"bookdown\"); \
		$(foreach output,$(formats),bookdown::render_book(\"report.Rmd\", \"$(output)\", config_file=\"report.yml\");)"
dockercmd = docker run --rm -it \
						--env-file $(env_file) \
						-v $(report_dir):$(report_dir) \
					$(reporter_image)


.PHONY: all

%/csv:
	echo Running benchmark $(dir $@)
	make -j -C $(dir $@) csv


all: $(env_file) $(foreach dir,$(benchmarks),$(dir)/csv)
	@echo "Building report using the following parameters:"
	@echo "Backend: $(backend) (override with argument backend=...)"
	@echo "Experiment description: $(experiment) (override with argument experiment=...)"
	@echo "Benchmarks: $(benchmarks) (override with argument benchmarks=...)"
	for bench in $(benchmarks); \
	do \
		cp -u ../runlogs/$$bench/* $(report_dir); \
		ln -f $$bench/*.Rmd $(report_dir); \
	done
	@echo "Compiling report..."
	@ln -f report.Rmd summary.Rmd common.R $(report_dir)
	@lscpu > $(report_dir)/lscpu.out
	@free -g > $(report_dir)/memory.out
	@nvidia-smi > $(report_dir)/gpu.out || { echo "No Nvidia GPU found" > $(report_dir)/gpu.out ; }
	@echo 'rmd_files: [ report.Rmd, $(report_files) summary.Rmd ]' > $(report_dir)/report.yml
	@cd $(report_dir); rm -rf _book* _main.Rmd
	cd $(report_dir); $(dockercmd) bash -c '$(Rcmd); chown -R $(local_id) $(report_dir)'
	cd $(report_dir); mv _book/_main.* .; rename s/_main/report/ _main.*


test:
	@echo 'rmd_files: [ report.Rmd, $(report_files) summary.Rmd ]'

$(env_file):
	mkdir -p $(report_dir)
	@echo "REPORTER_BACKEND=$(backend)" >> $(env_file)
	@echo "REPORTER_USER=$(USER)" >> $(env_file)
	@echo "REPORTER_GIT_HASH=$(shell git rev-parse --short HEAD)" >> $(env_file)
	@echo "REPORTER_HOSTNAME=$(shell hostname)" >> $(env_file)
	/usr/bin/env >> $(env_file)
