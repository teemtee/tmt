#
# Notes WRT help: a comment introduced by "##"...
#   - ... after a target specification will server as its help,
#   - ... at the beginning of line will serve as a target group separator.
#

# Prepare variables
TMP = $(CURDIR)/tmp

ccred=$(shell tput setaf 1)
ccgreen=$(shell tput setaf 2)
ccend=$(shell tput sgr0)

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

TMT_TEST_IMAGE_BASES = $(shell grep -rh 'FROM ' containers/ | cut -d' ' -f2 | sort | uniq)
TMT_TEST_IMAGE_TARGET_PREFIX = images-tests
TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX = tmt/tests/container

TMT_TEST_CONTAINER_IMAGES := $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/alpine:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/alpine/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/7:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/7/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/stream9:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/stream9/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/coreos:stable \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/coreos/ostree:stable \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/rawhide:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/rawhide/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/rawhide/unprivileged:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/41:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/41/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/41/unprivileged:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/40:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/40/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/40/unprivileged:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/39:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/39/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/39/unprivileged:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/ubi/8/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/ubuntu/22.04/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/debian/12.7/upstream:latest

TMT_TEST_IMAGES_TARGETS := $(foreach image,$(TMT_TEST_CONTAINER_IMAGES),images-tests/$(subst :,\:,$(image)))

images-tests: $(TMT_TEST_IMAGES_TARGETS)  ## Build customized images for tests
	podman images | grep 'localhost/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/' | sort

images-tests-bases:  ## Download base images for custom test images
	podman pull $(TMT_TEST_IMAGE_BASES)

define test-container-image-target-to-name =
$(subst $(TMT_TEST_IMAGE_TARGET_PREFIX)/,,${1})
endef

define build-test-container-image =
@ echo "$(ccgreen)Building $(ccred)$(call test-container-image-target-to-name,$@)$(ccend) $(ccgreen)image...$(ccend)"
podman build -t $(call test-container-image-target-to-name,${1}) -f ./containers/${2} .
@ echo
endef

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/alpine\:latest:
	$(call build-test-container-image,$@,alpine/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/alpine/upstream\:latest:
	$(call build-test-container-image,$@,alpine/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/7\:latest:
	$(call build-test-container-image,$@,centos/7/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/7/upstream\:latest:
	$(call build-test-container-image,$@,centos/7/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/stream9\:latest:
	$(call build-test-container-image,$@,centos/stream9/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/stream9/upstream\:latest:
	$(call build-test-container-image,$@,centos/stream9/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/coreos\:stable:
	$(call build-test-container-image,$@,fedora/coreos/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/coreos/ostree\:stable:
	$(call build-test-container-image,$@,fedora/coreos/ostree/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/rawhide\:latest:
	$(call build-test-container-image,$@,fedora/rawhide/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/rawhide/upstream\:latest:
	$(call build-test-container-image,$@,fedora/rawhide/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/rawhide/unprivileged\:latest:
	$(call build-test-container-image,$@,fedora/rawhide/Containerfile.unprivileged)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/41\:latest:
	$(call build-test-container-image,$@,fedora/41/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/41/upstream\:latest:
	$(call build-test-container-image,$@,fedora/41/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/41/unprivileged\:latest:
	$(call build-test-container-image,$@,fedora/41/Containerfile.unprivileged)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/40\:latest:
	$(call build-test-container-image,$@,fedora/40/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/40/upstream\:latest:
	$(call build-test-container-image,$@,fedora/40/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/40/unprivileged\:latest:
	$(call build-test-container-image,$@,fedora/40/Containerfile.unprivileged)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/39\:latest:
	$(call build-test-container-image,$@,fedora/39/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/39/upstream\:latest:
	$(call build-test-container-image,$@,fedora/39/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/39/unprivileged\:latest:
	$(call build-test-container-image,$@,fedora/39/Containerfile.unprivileged)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/ubi/8/upstream\:latest:
	$(call build-test-container-image,$@,ubi/8/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/ubuntu/22.04/upstream\:latest:
	$(call build-test-container-image,$@,ubuntu/22.04/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/debian/12.7/upstream\:latest:
	$(call build-test-container-image,$@,debian/12.7/Containerfile.upstream)

##
## Development
##
develop: _deps  ## Install development requirements
	sudo dnf install -y gcc git python3-nitrate {libvirt,krb5,libpq,python3}-devel jq podman buildah /usr/bin/python3.9

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

clean-test-images:  ## Remove all custom images built for tests
	for image in $(TMT_TEST_CONTAINER_IMAGES); do \
	    podman rmi -i "$$image"; \
	done

##
## Help!
##
help:: ## Show this help text
	@gawk -vG="$(ccgreen)" -vR="$(ccend)" ' \
	  match($$0, "^(([^#:]*[^ :]) *:)?([^#]*)##([^#].+|)$$",a) { \
	    if (a[2] != "") { printf "    make %s%-18s%s %s\n", G, a[2], R, a[4]; next }\
	    if (a[3] == "") { print a[4]; next }\
	    printf "\n%-36s %s\n","",a[4]\
	  }' $(MAKEFILE_LIST)
	@echo "" # blank line at the end
