# Create documentation files for functions using pydoc

paths := $(wildcard ../../fns/*/.)
VPATH := $(dir ${paths})
fns = $(subst /.,,$(subst ../../fns/,,${paths}))
docs = $(addsuffix .html, ${fns})

all: ${docs}

%.html: %.py
	pdoc -d google -o . ../../fns/*/*.py
#	python3 -m pydoc -w $^

clean:
	rm ${docs} index.html search.js
