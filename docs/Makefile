# Makefile for Sphinx documentation
#

.DEFAULT_GOAL := help

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
PAPER         =
BUILDDIR      = _build

# Internal variables.
PAPEROPT_a4     = -D latex_paper_size=a4
PAPEROPT_letter = -D latex_paper_size=letter
ALLSPHINXOPTS   = -d $(BUILDDIR)/doctrees $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) .
# the i18n builder cannot share the environment and doctrees with the others
I18NSPHINXOPTS  = $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) .

.PHONY: help generate-plugins plugins/*.rst generate-stories generate-autodocs clean html dirhtml singlehtml pickle json htmlhelp qthelp devhelp epub latex latexpdf text man changes linkcheck doctest coverage gettext

clean:
	rm -rf $(BUILDDIR) stories spec code/autodocs/*.rst

##
## Building documentation
##
html: generate  ## Make standalone HTML files
	$(SPHINXBUILD) -b html $(ALLSPHINXOPTS) $(BUILDDIR)/html
	@echo
	@echo "Build finished. The HTML pages are in $(BUILDDIR)/html."

latexpdf: generate  ## Make LaTeX files and run them through pdflatex
	$(SPHINXBUILD) -b latex $(ALLSPHINXOPTS) $(BUILDDIR)/latex
	@echo "Running LaTeX files through pdflatex..."
	$(MAKE) -C $(BUILDDIR)/latex all-pdf
	@echo "pdflatex finished; the PDF files are in $(BUILDDIR)/latex."

text: generate  ## Make text files
	$(SPHINXBUILD) -b text $(ALLSPHINXOPTS) $(BUILDDIR)/text
	@echo
	@echo "Build finished. The text files are in $(BUILDDIR)/text."

man: generate  ## Make manual pages
	$(SPHINXBUILD) -b man $(ALLSPHINXOPTS) $(BUILDDIR)/man
	@echo
	@echo "Build finished. The manual pages are in $(BUILDDIR)/man."

##
## Generate documentation sources from inputs
##
REPODIR       = ..
TMTDIR        = $(REPODIR)/tmt
SCRIPTSDIR    = scripts
TEMPLATESDIR  = templates

PLUGINS_TEMPLATE := $(TEMPLATESDIR)/plugins.rst.j2

generate: spec stories generate-lint-checks generate-plugins generate-stories generate-autodocs  ## Refresh all generated documentation sources

spec:
	mkdir -p spec

stories:
	mkdir -p stories

spec/lint.rst: $(SCRIPTSDIR)/generate-lint-checks.py $(TEMPLATESDIR)/lint-checks.rst.j2 $(TMTDIR)/base.py
	$(SCRIPTSDIR)/generate-lint-checks.py $(TEMPLATESDIR)/lint-checks.rst.j2 $@

plugins/discover.rst: $(SCRIPTSDIR)/generate-plugins.py $(PLUGINS_TEMPLATE) $(TMTDIR)/steps/discover/*.py
	$(SCRIPTSDIR)/generate-plugins.py discover $(PLUGINS_TEMPLATE) $@

plugins/execute.rst: $(SCRIPTSDIR)/generate-plugins.py $(PLUGINS_TEMPLATE) $(TMTDIR)/steps/execute/*.py
	$(SCRIPTSDIR)/generate-plugins.py execute $(PLUGINS_TEMPLATE) $@

plugins/finish.rst: $(SCRIPTSDIR)/generate-plugins.py $(PLUGINS_TEMPLATE) $(TMTDIR)/steps/finish/*.py
	$(SCRIPTSDIR)/generate-plugins.py finish $(PLUGINS_TEMPLATE) $@

plugins/prepare.rst: $(SCRIPTSDIR)/generate-plugins.py $(PLUGINS_TEMPLATE) $(TMTDIR)/steps/prepare/*.py
	$(SCRIPTSDIR)/generate-plugins.py prepare $(PLUGINS_TEMPLATE) $@

plugins/provision.rst: $(SCRIPTSDIR)/generate-plugins.py $(PLUGINS_TEMPLATE) $(TMTDIR)/steps/provision/*.py
	$(SCRIPTSDIR)/generate-plugins.py provision $(PLUGINS_TEMPLATE) $@

plugins/report.rst: $(SCRIPTSDIR)/generate-plugins.py $(PLUGINS_TEMPLATE) $(TMTDIR)/steps/report/*.py
	$(SCRIPTSDIR)/generate-plugins.py report $(PLUGINS_TEMPLATE) $@

plugins/test-checks.rst: $(SCRIPTSDIR)/generate-plugins.py $(PLUGINS_TEMPLATE) $(TMTDIR)/checks/*.py
	$(SCRIPTSDIR)/generate-plugins.py test-checks $(PLUGINS_TEMPLATE) $@

generate-lint-checks: spec spec/lint.rst  ## Generate documentation sources for lint checks

generate-stories: stories $(TEMPLATESDIR)/story.rst.j2  ## Generate documentation sources for stories
	$(SCRIPTSDIR)/generate-stories.py $(TEMPLATESDIR)/story.rst.j2

generate-plugins: plugins/discover.rst plugins/execute.rst plugins/finish.rst plugins/prepare.rst plugins/provision.rst plugins/report.rst plugins/test-checks.rst  ## Generate documentation sources for plugins

generate-autodocs:  ## Generate autodocs from source docstrings
	cd ../ && sphinx-apidoc --force --implicit-namespaces --no-toc -o docs/code/autodocs tmt

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
