# Makefile to generate additional sphinx sources
#

.DEFAULT_GOAL := help
.PHONY: help generate-stories generate-autodocs clean

clean:
	rm -rf stories spec autodocs/*.rst

##
## Generate documentation sources from inputs
##
REPODIR       = ..
TMTDIR        = $(REPODIR)/tmt
SCRIPTSDIR    = scripts

generate: spec stories generate-lint-checks generate-test-checks generate-stories generate-autodocs  ## Refresh all generated documentation sources

spec:
	mkdir -p spec

stories:
	mkdir -p stories

spec/lint.rst: $(SCRIPTSDIR)/generate-lint-checks.py lint-checks.rst.j2 $(TMTDIR)/base.py
	$(SCRIPTSDIR)/generate-lint-checks.py lint-checks.rst.j2 $@

spec/test-checks.rst: $(SCRIPTSDIR)/generate-test-checks.py test-checks.rst.j2 $(TMTDIR)/checks/*.py
	$(SCRIPTSDIR)/generate-test-checks.py test-checks.rst.j2 $@

generate-lint-checks: spec spec/lint.rst  ## Generate documentation sources for lint checks

generate-stories: stories  ## Generate documentation sources for stories
	$(SCRIPTSDIR)/generate-stories.py story.rst.j2

generate-test-checks: spec spec/test-checks.rst  ## Generate documentation sources for test checks

generate-autodocs:  ## Generate autodocs from source docstrings
	cd ../ && sphinx-apidoc --force --implicit-namespaces --no-toc -o docs/autodocs tmt

##
## Help!
##
help:: ## Show this help text
	@gawk -vG=$$(tput setaf 2) -vR=$$(tput sgr0) ' \
	  match($$0, "^(([^#:]*[^ :]) *:)?([^#]*)##([^#].+|)$$",a) { \
	    if (a[2] != "") { printf "    make %s%-22s%s %s\n", G, a[2], R, a[4]; next }\
	    if (a[3] == "") { print a[4]; next }\
	    printf "\n%-36s %s\n","",a[4]\
	  }' $(MAKEFILE_LIST)
	@echo "" # blank line at the end
