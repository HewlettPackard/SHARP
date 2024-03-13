# Global definitions and variables shared across benchmarks
#
# This file is only meant to be included by other Makefiles, not run on its own.
# It asserts that several standard variables need to be defined first by the
# including Makefile.

basedir := $(shell dirname $(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
outdir = $(basedir)/runlogs/$(id)
launcher = $(basedir)/launchers/launch.py --description "$(description)"
local_id = $(shell id -u):$(shell id -g)
formats = pdf_book # word_document2 gitbook powerpoint_presentation
$csv_files := $(foreach csv,$(outputs),$(outdir)/$(csv))

Rcmd=/usr/bin/env R -e \
		"setwd(\"$(outdir)\"); \
		library(\"bookdown\"); \
		$(foreach output,$(formats),bookdown::render_book(\"$(id).Rmd\", \"$(output)\", config_file=\"_bookdown.yml\");)"

# This function creates a report using R for a given experiment id and output format
# Currently set to use the reporter Docker container, but you can replace it with just executing $Rcmd directly
define generate_report
	/usr/bin/docker run --rm -it \
			-v $(basedir)/runlogs:$(basedir)/runlogs \
			reporter bash -c '$(Rcmd) ; chown -R $(local_id) $(outdir)'
endef

.PHONY: check-vars clean

# This needs to be the first rule in this Makefile to always run:
check-vars:
ifndef id
	$(error 'id' variable not set)
endif
ifndef outputs
	$(error 'outputs' variable not set)
endif
ifndef description
	$(error 'description' variable not set)
endif
	@echo "~~~~~~~~ Running benchmark $(id) ~~~~~~~~~~~"

# Rule for outputing a mini-report for a single benchmark
$(id).pdf: $(id).Rmd $(outputs)
	@rm -rf _main.Rmd
	$(call generate_report)
	mv $(outdir)/_book/_main.pdf $(outdir)/$(id).pdf

clean:
	@rm -rf csv
	cd $(outdir); /bin/rm -rf $(csv) *.pdf _book* *.csv

