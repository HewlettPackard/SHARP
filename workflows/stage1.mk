
repeats := 2
matsize := 2000
max_mpl := 12
launcher := ~/shasta/launchers/launch.py
all_csvs = $(foreach mpl, $(shell seq 1 $(max_mpl)), mpl-$(mpl).csv)

all: report.pdf
	echo done

report.pdf: $(all_csvs)
	@echo $(all_csvs)

mpl-%.csv:
	for r in $(shell seq 1 $(repeats)); \
	do \
		echo $(launcher) -n $* -t $(basename $@); \
	done

# Need to figure out:
# 1. Add a wrapper target like in parallel
# 2. if is_launched:
# 		a. Add foreach var with all CSVs, to propagate as dep; should work with expression or list
# 		b. Add pattern rule
# 3. else:
# 		a. propagate wrapper target as dep
# 		b. Add recipe to wrapper
#
# 		NO PATTERN RULES: expand list of targets manually. replace loop var with value (not @*). Make sequential or parallel. Last step is dep carried forward. No need for wrapper target?
