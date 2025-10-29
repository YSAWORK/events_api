# ./Makefile
# Makefile for importing events or running benchmarks.

# ===== CONFIGURATION =====
PYTHON := python
PYTHONPATH := $(CURDIR)

# CSV import
IMPORT_MODULE := src.endpoint_events.cli_utils
CSV := $(word 2, $(MAKECMDGOALS))

# Benchmarks
BENCHMARK_MOD := src.benchmarks.run_benchmarks

# ===== HELP =====
help:
	@echo "Usage:"
	@echo "  make import_events path/to.csv     - Import events from CSV"
	@echo "  make run_api                       - Start FastAPI app"
	@echo "  make benchmark                     - Run whole benchmark module ($(BENCHMARK_MOD))"
	@echo "  make benchmark_func [FUNC=...]     - Run specific function from benchmark module (default: $(FUNC))"


# ===== TARGETS =====
## Import events from CSV
import_events:
	@if [ "$(word 2,$(MAKECMDGOALS))" = "" ]; then \
		echo "Usage: make import_events <path-to-csv>"; exit 1; \
	fi
	@CSV=$(word 2,$(MAKECMDGOALS)); \
	if [ ! -f "$$CSV" ]; then \
		echo "File not found: $$CSV"; exit 1; \
	fi; \
	echo "Importing events from $$CSV to database..."; \
	PYTHONPATH="$(CURDIR)" $(PYTHON) -m $(IMPORT_MODULE) "$$CSV"

# ===== API RUN =====
run_api:
	@echo "Starting FastAPI server..."
	@PYTHONPATH="$(PYTHONPATH)" $(PYTHON) -m src.main

# ===== BENCHMARKS =====
# Run the whole benchmark module (executes __main__)
benchmark:
	@echo "Running full benchmark module..."
	@PYTHONPATH="$(PYTHONPATH)" $(PYTHON) -m $(BENCHMARK_MOD)

# Run only test_100k_dau() directly
benchmark_func:
	@echo "Running test_100k_dau() ..."
	@PYTHONPATH="$(PYTHONPATH)" $(PYTHON) -c "from src.benchmarks.run_test import test_100k_dau; test_100k_dau()"

%:
	@: