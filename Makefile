# Development shortcuts. Run `make help` to list them.
PYTHON ?= .venv/bin/python
POT = po/handcue.pot
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' src/handcue/__init__.py)

.PHONY: help venv run test lint lock i18n-extract i18n-update i18n-compile build deb clean

help:
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

venv: ## Create .venv and install the app in editable mode with dev tools
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

run: i18n-compile ## Run the app from the source tree
	$(PYTHON) -m handcue

test: ## Run the test suite
	$(PYTHON) -m pytest -q

lint: ## Check the code with ruff
	$(PYTHON) -m ruff check src tests examples hatch_build.py

lock: ## Regenerate requirements.lock (hashes) from requirements.in
	$(PYTHON) -m piptools compile --quiet --generate-hashes --allow-unsafe --strip-extras --no-header \
		--output-file requirements.lock requirements.in

i18n-extract: ## Refresh po/handcue.pot from the source
	$(PYTHON) -m babel.messages.frontend extract -F babel.cfg -k _ -k ngettext:1,2 --no-wrap \
		--sort-by-file --project=handcue --version=$(VERSION) --copyright-holder="Ignacio Aranda" \
		--msgid-bugs-address="https://github.com/Ignacio-Aranda/handcue/issues" -o $(POT) src

i18n-update: i18n-extract ## Merge new strings into every po/*.po
	for po in po/*.po; do \
		$(PYTHON) -m babel.messages.frontend update -i $(POT) -o $$po -l $$(basename $$po .po) --no-wrap; \
	done

i18n-compile: ## Compile po/*.po for running from source
	$(PYTHON) -c "import hatch_build; hatch_build.compile_translations('.')"

build: ## Build the sdist and wheel into dist/
	$(PYTHON) -m build

deb: ## Build a .deb for this system into dist/
	packaging/deb/build.sh

clean:
	rm -rf build dist src/handcue/locale .pytest_cache .ruff_cache
