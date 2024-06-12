# Makefile to generate additional sphinx sources
#

.DEFAULT_GOAL := help
.PHONY: help generate-plugins plugins/*.rst generate-stories generate-template-filters generate-autodocs clean

clean:
	rm -rf _build stories spec code/autodocs/*.rst code/template-filters.rst
	find plugins -name "*.rst" ! -name index.rst | xargs rm -f

##
## Generate documentation sources from inputs
##
REPODIR       = ..
TMTDIR        = $(REPODIR)/tmt
SCRIPTSDIR    = scripts
TEMPLATESDIR  = templates

PLUGINS_TEMPLATE := $(TEMPLATESDIR)/plugins.rst.j2

generate: spec stories generate-lint-checks generate-template-filters generate-plugins generate-stories generate-autodocs  ## Refresh all generated documentation sources

spec:
	mkdir -p spec

stories:
	mkdir -p stories

spec/lint.rst: $(SCRIPTSDIR)/generate-lint-checks.py $(TEMPLATESDIR)/lint-checks.rst.j2 $(TMTDIR)/base.py
	$(SCRIPTSDIR)/generate-lint-checks.py $(TEMPLATESDIR)/lint-checks.rst.j2 $@

code/template-filters.rst: $(SCRIPTSDIR)/generate-template-filters.py $(TEMPLATESDIR)/template-filters.rst.j2 $(TMTDIR)/utils/templates.py
	$(SCRIPTSDIR)/generate-template-filters.py $(TEMPLATESDIR)/template-filters.rst.j2 $@

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

generate-template-filters: code/template-filters.rst  ## Generate documentation sources for Jinja2 template filters

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
