#
# Makefile to generate additional sphinx sources
#

# Path to repository root
REPODIR = ..

# Path to tmt source directory
TMTDIR = $(REPODIR)/tmt

# Path to docs source directory
DOCSDIR = $(REPODIR)/docs

# A list of directories that are completely generated
GENERATED_DIRECTORIES = spec stories

.DEFAULT_GOAL := help

.PHONY: help \
        $(GENERATED_DIRECTORIES) \
        clean

#
# Targets creating directories for generated documentation sources
#
$(GENERATED_DIRECTORIES): %:
	mkdir -p $@

#
# Various targets for generating documentation source files from templates
#

clean:  ## Remove all generated content
	rm -rf _build $(GENERATED_DIRECTORIES) code/autodocs/*.rst code/template-extensions.rst plugins/hardware-matrix.rst guide/test-runner-guest-compatibility-matrix.inc.rst $(PLUGIN_TARGETS)

##
## Help!
##
help:: ## Show this help text
	@gawk -vG=$$(tput setaf 2) -vR=$$(tput sgr0) ' \
	  match($$0, "^(([^#:]*[^ :]) *:)?([^#]*)##([^#].+|)$$",a) { \
	    if (a[2] != "") { printf "    make %s%-26s%s %s\n", G, a[2], R, a[4]; next }\
	    if (a[3] == "") { print a[4]; next }\
	    printf "\n%-36s %s\n","",a[4]\
	  }' $(MAKEFILE_LIST)
	@echo "" # blank line at the end
