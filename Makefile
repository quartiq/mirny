.PHONY: all
all: build

.PHONY: prep
prep:
	python3 -m venv --system-site-packages .venv
	./.venv/bin/pip install -r requirements.txt

.PHONY: build
build: build/mirny.vm6

build/mirny.vm6: mirny.py mirny_cpld.py mirny_impl.py
	python3 mirny_impl.py

REV:=$(shell git describe --always --abbrev=8 --dirty)

.PHONY: release
release: build/mirny.vm6
	cd build; tar czvf mirny_$(REV).tar.gz \
		mirny.v mirny.ucf mirny.xst \
		mirny.vm6 mirny.jed mirny.isc \
		mirny.tim mirny.rpt \
		mirny.pad mirny_pad.csv
