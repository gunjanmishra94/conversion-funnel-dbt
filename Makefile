# Common commands for the project. Run `make` to list them.
# Needs Python 3.10 or newer; override with e.g. `make setup PYTHON=python3.11`.

PYTHON ?= python3.12
DBT := DBT_PROFILES_DIR=$(CURDIR) .venv/bin/dbt
DATABASE := data/interview_assignment.duckdb

.DEFAULT_GOAL := help
.PHONY: help setup debug run test build clean dashboard-setup dashboard

help:  ## List the available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-16s %s\n", $$1, $$2}'

setup: .venv/bin/dbt  ## Create the virtual environment and install dbt

.venv/bin/dbt: requirements.txt
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r requirements.txt

$(DATABASE):
	@echo "Missing $(DATABASE). Put the provided database file there." && exit 1

debug: setup $(DATABASE)  ## Check the dbt connection
	$(DBT) debug

run: setup $(DATABASE)  ## Build the models
	$(DBT) run

test: setup $(DATABASE)  ## Run the tests
	$(DBT) test

build: setup $(DATABASE)  ## Build the models and run the tests
	$(DBT) build

clean:  ## Remove dbt's build output (target/, dbt_packages/)
	$(DBT) clean

dashboard-setup: dashboard/.venv/bin/streamlit  ## Install the dashboard's own environment

dashboard/.venv/bin/streamlit: dashboard/requirements.txt
	$(PYTHON) -m venv dashboard/.venv
	dashboard/.venv/bin/pip install -r dashboard/requirements.txt

dashboard: dashboard-setup $(DATABASE)  ## Start the Streamlit dashboard (run `make build` first)
	cd dashboard && .venv/bin/streamlit run app.py
