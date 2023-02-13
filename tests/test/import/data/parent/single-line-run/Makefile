export TEST=/single-line-run
export TESTVERSION=1.0

FILES=$(METADATA) Makefile

.PHONY: all run clean

run: $(FILES)
	bash -x runtest.sh

clean:
	rm -f *~

include /usr/share/rhts/lib/rhts-make.include

$(METADATA): Makefile
	@echo "Owner:           Name <nobody@localhost.localdomain>" > $(METADATA)
	@echo "Name:            $(TEST)" >> $(METADATA)
	@echo "TestTime:        5m" >> $(METADATA)
	@echo "TestVersion:     $(TESTVERSION)" >> $(METADATA)
	@echo "Path:            $(TEST_DIR)" >> $(METADATA)
	@echo "Requires:        " >> $(METADATA)
	@echo "RhtsRequires:    foo bar" >> $(METADATA)
	@echo "Description:     Target run having a single line" >> $(METADATA)
	@echo "License:         MIT" >> $(METADATA)

	rhts-lint $(METADATA)
