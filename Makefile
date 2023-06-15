# Prepare variables
TMP = $(CURDIR)/tmp
VERSION = $(shell grep ^Version tmt.spec | sed 's/.* //')
COMMIT = $(shell git rev-parse --short HEAD)
REPLACE_VERSION = "s/running from the source/$(VERSION) ($(COMMIT))/"
PACKAGE = tmt-$(VERSION)
FILES = LICENSE README.rst \
		Makefile tmt.spec setup.py \
		examples tmt bin tests .fmf

# Define special targets
all: docs packages
.PHONY: docs

# Temporary directory, include .fmf to prevent exploring tests there
tmp:
	mkdir -p $(TMP)/.fmf


# Run the test suite, optionally with coverage
test: tmp
	python3 -m pytest -vvv -ra --showlocals tests/unit
smoke: tmp
	python3 -m pytest -vvv -ra --showlocals tests/unit/test_cli.py
coverage: tmp
	coverage run --source=tmt,bin -m pytest -vvv -ra --showlocals tests
	coverage report
	coverage annotate
# Regenerate test data for integration tests
# remove selected/all response files in tests/integration/test_data directory
requre:
	cd tests/integration; python3 -m pytest -vvv -ra --showlocals
	# response files cleanup
	requre-patch purge --replaces :milestone_url:str:SomeText --replaces :latency:float:0 tests/integration/test_data/test_nitrate/*


# Build documentation, prepare man page
docs: man
	cd docs && make html
man: source
	cp docs/header.txt $(TMP)/man.rst
	tail -n+8 README.rst >> $(TMP)/man.rst
	rst2man $(TMP)/man.rst > $(TMP)/$(PACKAGE)/tmt.1


# RPM packaging and Packit
source: clean tmp
	mkdir -p $(TMP)/SOURCES
	mkdir -p $(TMP)/$(PACKAGE)
	cp -a $(FILES) $(TMP)/$(PACKAGE)
	sed -i $(REPLACE_VERSION) $(TMP)/$(PACKAGE)/tmt/__init__.py
tarball: source man
	cd $(TMP) && tar cfz SOURCES/$(PACKAGE).tar.gz $(PACKAGE)
	@echo ./tmp/SOURCES/$(PACKAGE).tar.gz
version:
	@echo "$(VERSION)"
rpm: tarball
	rpmbuild --define '_topdir $(TMP)' -bb tmt.spec
srpm: tarball
	rpmbuild --define '_topdir $(TMP)' -bs tmt.spec
packages: rpm srpm
bump2dev:
	$(shell sed "s/^Version:.*/Version: $$(echo $(VERSION) | awk '{ split($$0,v,"."); printf "%s.%s.dev", v[1], v[2]+1 }')/" -i tmt.spec)


# Containers
images:
	podman build -t tmt --squash -f ./containers/Dockerfile.mini .
	podman build -t tmt-all --squash -f ./containers/Dockerfile.full .


# Python packaging
wheel:
	cp -a tmt/__init__.py tmt/__init__.py.backup
	sed -i $(REPLACE_VERSION) tmt/__init__.py
	python3 setup.py bdist_wheel
	mv tmt/__init__.py.backup tmt/__init__.py
upload:
	twine upload dist/*.whl


# Git vim tags and cleanup
tags:
	find tmt -name '*.py' | xargs ctags --python-kinds=-i
clean:
	rm -rf $(TMP) build dist .cache
	rm -rf docs/{_build,stories,spec}
	find . -type f -name "*.py[co]" -delete
	find . -type f -name "*,cover" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name .pytest_cache -exec rm -rv {} +
	rm -f .coverage tags
	rm -rf examples/convert/{main.fmf,test.md,Manual}
	rm -f tests/full/repo_copy.tgz
