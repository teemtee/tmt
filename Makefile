#
# Notes WRT help: a comment introduced by "##"...
#   - ... after a target specification will server as its help,
#   - ... at the beginning of line will serve as a target group separator.
#

# Prepare variables
TMP = $(CURDIR)/tmp

ccred=$(shell env TERM="$${TERM:-linux}" tput setaf 1)
ccgreen=$(shell env TERM="$${TERM:-linux}" tput setaf 2)
ccend=$(shell env TERM="$${TERM:-linux}" tput sgr0)

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

# Base images of our tmt container images, collected from `FROM ...` directives in Containerfiles.
TMT_DISTRO_IMAGE_BASES = $(shell grep -h 'FROM ' containers/Containerfile.* | cut -d' ' -f2 | sort | uniq)

# All tmt image targets will begin with this string.
TMT_DISTRO_IMAGE_TARGET_PREFIX = images

# All tmt container images will begin with this string.
TMT_DISTRO_CONTAINER_IMAGE_NAME_PREFIX = tmt/container

# The list of tmt container images.
TMT_DISTRO_CONTAINER_IMAGES := $(TMT_DISTRO_CONTAINER_IMAGE_NAME_PREFIX)/tmt:latest \
                               $(TMT_DISTRO_CONTAINER_IMAGE_NAME_PREFIX)/tmt-all:latest

# The list of targets building individual tmt images.
TMT_DISTRO_IMAGES_TARGETS := $(foreach image,$(TMT_DISTRO_CONTAINER_IMAGES),images/$(subst :,\:,$(image)))

# Base images of our test images, collected from `FROM ...` directives in Containerfiles
TMT_TEST_IMAGE_BASES = $(shell grep -rh 'FROM ' containers/ | cut -d' ' -f2 | sort | uniq)

# All tmt test image targets will begin with this string.
TMT_TEST_IMAGE_TARGET_PREFIX = images/test

# All tmt test container images will begin with this string.
TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX = tmt/container/test

# The list of tmt test container images.
TMT_TEST_CONTAINER_IMAGES := $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/alpine:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/alpine/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/7:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/7/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/stream9:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/stream9/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/stream10:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/stream10/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/coreos:stable \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/coreos/ostree:stable \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/latest:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/latest/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/latest/unprivileged:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/rawhide:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/rawhide/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/rawhide/unprivileged:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/41:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/41/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/41/unprivileged:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/40:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/40/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/40/unprivileged:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/ubi/8/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/ubuntu/22.04/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/debian/12.7/upstream:latest \
                             $(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/latest/bootc:latest

# The list of targets building individual tmt test images.
TMT_TEST_IMAGES_TARGETS := $(foreach image,$(TMT_TEST_CONTAINER_IMAGES),images/test/$(subst :,\:,$(image)))

images: $(TMT_DISTRO_IMAGES_TARGETS)  ## Build tmt images for podman/docker
	podman images | grep 'localhost/$(TMT_DISTRO_CONTAINER_IMAGE_NAME_PREFIX)/' | sort

images/test: $(TMT_TEST_IMAGES_TARGETS)  ## Build customized images for tests
	podman images | grep 'localhost/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/' | sort

images/test/bases:  ## Download base images for custom test images
	podman pull $(TMT_TEST_IMAGE_BASES)

# Build a single container: <image name> <containerfile>
define do-build-container-image =
@ echo "$(ccred)$$(date '+%Y-%m-%d %H:%M:%S')$(ccend) $(ccgreen)Building$(ccend) $(ccred)${1}$(ccend) $(ccgreen)image...$(ccend)"
podman build ${3} -t ${1} -f ./containers/${2} .
@ echo "$(ccred)$$(date '+%Y-%m-%d %H:%M:%S')$(ccend) $(ccgreen)Building$(ccend) $(ccred)${1}$(ccend) $(ccgreen)image done$(ccend)"
endef

# Return an image name from the given target: <image target>
define container-image-target-to-name =
$(subst $(TMT_DISTRO_IMAGE_TARGET_PREFIX)/,,${1})
endef

# Return a test image name from the given target: <image target>
define test-container-image-target-to-name =
$(subst $(TMT_TEST_IMAGE_TARGET_PREFIX)/,,${1})
endef

# Build tmt image: <image name> <containerfile>
define build-container-image =
$(call do-build-container-image,$(call container-image-target-to-name,${1}),${2},--squash)
endef

# Build tmt test image: <image name> <containerfile>
define build-test-container-image =
$(call do-build-container-image,$(call test-container-image-target-to-name,${1}),${2},)
endef

$(TMT_DISTRO_IMAGE_TARGET_PREFIX)/$(TMT_DISTRO_CONTAINER_IMAGE_NAME_PREFIX)/tmt\:latest:
	$(call build-container-image,$@,Containerfile.mini)

$(TMT_DISTRO_IMAGE_TARGET_PREFIX)/$(TMT_DISTRO_CONTAINER_IMAGE_NAME_PREFIX)/tmt-all\:latest:
	$(call build-container-image,$@,Containerfile.full)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/alpine\:latest:
	$(call build-test-container-image,$@,alpine/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/alpine/upstream\:latest:
	$(call build-test-container-image,$@,alpine/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/7\:latest:
	$(call build-test-container-image,$@,centos/7/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/7/upstream\:latest:
	$(call build-test-container-image,$@,centos/7/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/stream10\:latest:
	$(call build-test-container-image,$@,centos/stream10/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/centos/stream10/upstream\:latest:
	$(call build-test-container-image,$@,centos/stream10/Containerfile.upstream)

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

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/latest\:latest:
	$(call build-test-container-image,$@,fedora/latest/Containerfile)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/latest/upstream\:latest:
	$(call build-test-container-image,$@,fedora/latest/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/latest/unprivileged\:latest:
	$(call build-test-container-image,$@,fedora/latest/Containerfile.unprivileged)

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

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/ubi/8/upstream\:latest:
	$(call build-test-container-image,$@,ubi/8/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/ubuntu/22.04/upstream\:latest:
	$(call build-test-container-image,$@,ubuntu/22.04/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/debian/12.7/upstream\:latest:
	$(call build-test-container-image,$@,debian/12.7/Containerfile.upstream)

$(TMT_TEST_IMAGE_TARGET_PREFIX)/$(TMT_TEST_CONTAINER_IMAGE_NAME_PREFIX)/fedora/latest/bootc\:latest:
	$(call build-test-container-image,$@,fedora/latest/bootc/Containerfile)
##
## Development
##
develop: _deps  ## Install development requirements
	sudo dnf install -y expect gcc git python3-nitrate {libvirt,krb5,libpq,python3}-devel jq podman buildah /usr/bin/python3.9

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

clean/images:  ## Remove tmt images
	for image in $(TMT_DISTRO_CONTAINER_IMAGES); do \
	    podman rmi -i "$$image"; \
	done

clean/images/test:  ## Remove all custom images built for tests
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
