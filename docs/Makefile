#
# Makefile to generate additional sphinx sources
#

# Path to repository root
REPODIR = ..

# Path to tmt source directory
TMTDIR = $(REPODIR)/tmt

# Path to docs source directory
DOCSDIR = $(REPODIR)/docs

# Path to directory with scripts generating documentation sources
SCRIPTSDIR = scripts

# Path to directory with templates to use for generating documentation sources
TEMPLATESDIR = templates

# Path to a template for rendering plugin documentation sources
PLUGINS_TEMPLATE = $(TEMPLATESDIR)/plugins.rst.j2

# A list of directories that are completely generated
GENERATED_DIRECTORIES = spec stories

# A list of tmt step names
STEPS = discover provision prepare execute finish report

# A list of `plugins/*.rst` files to generate
PLUGIN_TARGETS = $(addsuffix .rst,$(addprefix plugins/,$(STEPS))) plugins/prepare-feature.rst plugins/test-checks.rst

.DEFAULT_GOAL := help

.PHONY: help \
        $(GENERATED_DIRECTORIES) \
        generate-plugins \
        $(PLUGIN_TARGETS) \
        generate-stories \
        generate-template-extensions \
        generate-autodocs clean

##
## Generate documentation sources from inputs
##
generate: $(LOGO_DST) generate-runner-guest-matrix generate-lint-checks generate-template-extensions generate-plugins generate-stories generate-autodocs  ## Refresh all generated documentation sources

#
# Targets creating directories for generated documentation sources
#
$(GENERATED_DIRECTORIES): %:
	mkdir -p $@

#
# Various targets for generating documentation source files from templates
#

# Extract $step from a `plugins/$step.rst` target
define plugins-to-step =
$(subst plugins/,,$(subst .rst,,${1}))
endef

# Render a list of dependencies of a `plugins/$step.rst` target
define plugins-dependencies =
$(SCRIPTSDIR)/generate-plugins.py $(PLUGINS_TEMPLATE) $(TMTDIR)/steps/__init__.py $(TMTDIR)/steps/$(call plugins-to-step,$@)/*.py
endef

# Render a list of dependencies of a `plugins/feature.rst` target
define plugins-feature-dependencies =
$(SCRIPTSDIR)/generate-plugins.py $(PLUGINS_TEMPLATE) $(TMTDIR)/steps/__init__.py $(TMTDIR)/steps/prepare/__init__.py $(TMTDIR)/steps/prepare/feature/*.py
endef

# Render a list of dependencies of a `plugins/test-checks.rst` target
define plugins-checks-dependencies =
$(SCRIPTSDIR)/generate-plugins.py $(PLUGINS_TEMPLATE) $(TMTDIR)/steps/__init__.py $(TMTDIR)/checks/*.py
endef

# Generate plugin documentation sources for a given step
define build-plugins =
$(SCRIPTSDIR)/generate-plugins.py $(call plugins-to-step,$@) $(PLUGINS_TEMPLATE) $@
endef

code/template-extensions.rst: $(SCRIPTSDIR)/generate-template-extensions.py \
                              $(TEMPLATESDIR)/template-extensions.rst.j2 \
                              $(TMTDIR)/utils/templates.py
	$(SCRIPTSDIR)/generate-template-extensions.py $(TEMPLATESDIR)/template-extensions.rst.j2 $@

plugins/discover.rst: $(call plugins-dependencies)
	$(call build-plugins)

plugins/execute.rst: $(call plugins-dependencies)
	$(call build-plugins)

plugins/finish.rst: $(call plugins-dependencies)
	$(call build-plugins)

plugins/prepare.rst: $(call plugins-dependencies)
	$(call build-plugins)

plugins/provision.rst: $(call plugins-dependencies)
	$(call build-plugins)

plugins/report.rst: $(call plugins-dependencies)
	$(call build-plugins)

plugins/prepare-feature.rst: $(call plugins-feature-dependencies)
	$(call build-plugins)

plugins/test-checks.rst: $(call plugins-checks-dependencies)
	$(call build-plugins)

plugins/hardware-matrix.rst: $(SCRIPTSDIR)/generate-hardware-matrix.py \
                          $(TEMPLATESDIR)/hardware-matrix.rst.j2 \
                          $(shell find $(REPODIR)/spec/hardware -name '*.fmf')
	$(SCRIPTSDIR)/generate-hardware-matrix.py $(TEMPLATESDIR)/hardware-matrix.rst.j2 $@

guide/test-runner-guest-compatibility-matrix.inc.rst: $(SCRIPTSDIR)/generate-test-runner-guest-matrix.py \
                                                      $(TEMPLATESDIR)/test-runner-guest-compatibility-matrix.inc.rst.j2 \
                                                      $(DOCSDIR)/test-runner-guest-compatibility.yaml
	$(SCRIPTSDIR)/generate-test-runner-guest-matrix.py $(TEMPLATESDIR)/test-runner-guest-compatibility-matrix.inc.rst.j2 $(DOCSDIR)/test-runner-guest-compatibility.yaml $@

spec/lint.rst: $(SCRIPTSDIR)/generate-lint-checks.py \
               $(TEMPLATESDIR)/lint-checks.rst.j2 \
               $(TMTDIR)/base.py
	$(SCRIPTSDIR)/generate-lint-checks.py $(TEMPLATESDIR)/lint-checks.rst.j2 $@

#
# Top-level targets to generate documentation sources
#
generate-autodocs:  ## Generate autodocs from source docstrings
	cd ../ && sphinx-apidoc --force --implicit-namespaces --no-toc -o docs/code/autodocs tmt

generate-lint-checks: spec spec/lint.rst  ## Generate documentation sources for lint checks

generate-plugins: $(PLUGIN_TARGETS) generate-hardware-matrix  ## Generate documentation sources for plugins

generate-hardware-matrix: plugins/hardware-matrix.rst  ## Generate HW requirement support matrix

generate-runner-guest-matrix: guide/test-runner-guest-compatibility-matrix.inc.rst  ## Generate runner vs. guest compatibility matrix

generate-stories: stories $(TEMPLATESDIR)/story.rst.j2  ## Generate documentation sources for stories
	$(SCRIPTSDIR)/generate-stories.py $(TEMPLATESDIR)/story.rst.j2

generate-template-extensions: code/template-extensions.rst  ## Generate documentation sources for Jinja2 template extensions

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
