# Prepare variables
TMP = $(CURDIR)/tmp

# Define special targets
all: docs packages
.PHONY: docs

# Temporary directory, include .fmf to prevent exploring tests there
tmp:
	mkdir -p $(TMP)/.fmf

# Run the test suite, optionally with coverage
test: tmp
	hatch run test:unit
smoke: tmp
	hatch run test:smoke
coverage: tmp nitrateconf
	hatch run test:coverage
nitrateconf:
	test -e ~/.nitrate || echo -en '[nitrate]\nurl = https://nitrate.server/xmlrpc/\n' | tee ~/.nitrate

# Regenerate test data for integration tests
# remove selected/all response files in tests/integration/test_data directory
requre:
	hatch run test:requre

# Build documentation, prepare man page
docs: clean
	hatch run docs:html
man:
	hatch run docs:man

# Packaging and Packit
build: clean man
	hatch build
tarball: clean tmp build
	mkdir -p $(TMP)/SOURCES
	cp dist/tmt-*.tar.gz $(TMP)/SOURCES
rpm: tarball ver2spec
	# If the build system is missing the required dependencies, use nosrc.rpm to install them
	rpmbuild --define '_topdir $(TMP)' -bb tmt.spec || echo 'Hint: run `make deps` to install build dependencies'
srpm: tarball ver2spec
	rpmbuild --define '_topdir $(TMP)' -bs tmt.spec
deps: tarball ver2spec
	rpmbuild --define '_topdir $(TMP)' -br tmt.spec || sudo dnf builddep $(TMP)/SRPMS/tmt-*buildreqs.nosrc.rpm
packages: rpm srpm
version:
	hatch version
ver2spec:
	$(shell sed -E "s/^(Version:[[:space:]]*).*/\1$$(hatch version)/" -i tmt.spec)

# Containers
images:
	podman build -t tmt --squash -f ./containers/Containerfile.mini .
	podman build -t tmt-all --squash -f ./containers/Containerfile.full .

# Development
develop:
	sudo dnf --setopt=install_weak_deps=False install hatch gcc make git rpm-build python3-nitrate {python3,libvirt,krb5,libpq}-devel jq podman

# Git vim tags and cleanup
tags:
	find tmt -name '*.py' | xargs ctags --python-kinds=-i
clean:
	rm -rf $(TMP) build dist tmt.1
	rm -rf .cache .mypy_cache .ruff_cache
	rm -rf docs/{_build,stories,spec}
	find . -type f -name "*.py[co]" -delete
	find . -type f -name "*,cover" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name .pytest_cache -exec rm -rv {} +
	rm -f .coverage tags
	rm -rf examples/convert/{main.fmf,test.md,Manual} Manual
	rm -f tests/full/repo_copy.tgz
