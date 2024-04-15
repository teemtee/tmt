#
# Notes WRT help: a comment introduced by "##"...
#   - ... after a target specification will server as its help,
#   - ... at the beginning of line will serve as a target group separator.
#

# Prepare variables
TMP = $(CURDIR)/tmp
UNIT_TESTS_IMAGE_TAG = tmt-unit-tests

# Define special targets
.DEFAULT_GOAL := help
.PHONY: docs

all: docs packages  ## Generate docs and packages

# Temporary directory, include .fmf to prevent exploring tests there
tmp:
	mkdir -p $(TMP)/.fmf

##
## Run the tests
##
test: tmp  ## Run the test suite
	hatch run test:unit

smoke: tmp  ## Run the smoke-level part of the test suite
	hatch run test:smoke

coverage: tmp nitrateconf  ## Run the test suite with coverage enabled
	hatch run test:coverage

nitrateconf:
	test -e ~/.nitrate || echo -en '[nitrate]\nurl = https://nitrate.server/xmlrpc/\n' | tee ~/.nitrate

# remove selected/all response files in tests/integration/test_data directory
requre:  ## Regenerate test data for integration tests
	hatch run test:requre

##
## Documentation
##
docs: clean  ## Build documentation
	hatch run docs:html

man:  ## Build man page
	hatch run docs:man

##
## Packaging & Packit
##
build: clean man
	hatch build
tarball: clean tmp build
	mkdir -p $(TMP)/SOURCES
	cp dist/tmt-*.tar.gz $(TMP)/SOURCES

rpm: tarball ver2spec  ## Build RPMs
	# If the build system is missing the required dependencies, use nosrc.rpm to install them
	rpmbuild --define '_topdir $(TMP)' -bb tmt.spec || echo 'Hint: run `make deps` to install build dependencies'

srpm: tarball ver2spec  ## Build SRPM
	rpmbuild --define '_topdir $(TMP)' -bs tmt.spec

_deps:  # Minimal dependencies (common for 'deps' and 'develop' targets)
	sudo dnf install -y hatch python3-devel python3-hatch-vcs rpm-build

build-deps: _deps tarball ver2spec  ## Install build dependencies
	rpmbuild --define '_topdir $(TMP)' -br tmt.spec || sudo dnf builddep -y $(TMP)/SRPMS/tmt-*buildreqs.nosrc.rpm

packages: rpm srpm  ## Build RPM and SRPM packages

version:  ## Build tmt version for packaging purposes
	hatch version

ver2spec:
	$(shell sed -E "s/^(Version:[[:space:]]*).*/\1$$(hatch version)/" -i tmt.spec)

##
## Containers
##
images:  ## Build tmt images for podman/docker
	podman build -t tmt --squash -f ./containers/Containerfile.mini .
	podman build -t tmt-all --squash -f ./containers/Containerfile.full .

images-unit-tests: image-unit-tests-alpine image-unit-tests-coreos  ## Build images for unit tests

image-unit-tests-alpine:  ## Build local alpine image for unit tests
	podman build -t alpine:$(UNIT_TESTS_IMAGE_TAG) -f ./containers/Containerfile.alpine .

image-unit-tests-coreos:  ## Build local CoreOS image for unit tests
	podman build -t fedora-coreos:$(UNIT_TESTS_IMAGE_TAG) -f ./containers/Containerfile.coreos .

##
## Development
##
develop: _deps  ## Install development requirements
	sudo dnf install -y gcc git python3-nitrate {libvirt,krb5,libpq,python3}-devel jq podman buildah

# Git vim tags and cleanup
tags:
	find tmt -name '*.py' | xargs ctags --python-kinds=-i

clean:  ## Remove all temporary files, packaging artifacts and docs
	rm -rf $(TMP) build dist tmt.1
	rm -rf .cache .mypy_cache .ruff_cache
	make -C docs clean
	find . -type f -name "*.py[co]" -delete
	find . -type f -name "*,cover" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name .pytest_cache -exec rm -rv {} +
	rm -f .coverage tags
	rm -rf examples/convert/{main.fmf,test.md,Manual} Manual
	rm -f tests/full/repo_copy.tgz

##
## Help!
##
help:: ## Show this help text
	@gawk -vG=$$(tput setaf 2) -vR=$$(tput sgr0) ' \
	  match($$0, "^(([^#:]*[^ :]) *:)?([^#]*)##([^#].+|)$$",a) { \
	    if (a[2] != "") { printf "    make %s%-18s%s %s\n", G, a[2], R, a[4]; next }\
	    if (a[3] == "") { print a[4]; next }\
	    printf "\n%-36s %s\n","",a[4]\
	  }' $(MAKEFILE_LIST)
	@echo "" # blank line at the end
