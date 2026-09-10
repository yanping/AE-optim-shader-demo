# ==============================================================================
# Google Cloud AlphaEvolve Shader Optimization Framework Makefile
# ==============================================================================

VENV ?= ./venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PLAYWRIGHT := $(VENV)/bin/playwright
PYTEST := $(VENV)/bin/pytest

PROJECT ?= 01
PROGRAMS ?= 50
ITERATIONS ?= $(PROGRAMS)
SHADER ?=

.DEFAULT_GOAL := help

.PHONY: help setup auth run report profile baseline test clean

help: ## Show available targets and usage
	@echo "\033[1;34mAlphaEvolve Shader Optimization Framework\033[0m"
	@echo "Usage: make \033[36m<target>\033[0m [PROJECT=<id>] [PROGRAMS=<n>] [SHADER=<path>]\n"
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make setup                          # Set up venv and install dependencies"
	@echo "  make auth                           # Authenticate with Google Cloud ADC"
	@echo "  make run PROJECT=01                 # Run AlphaEvolve on project 01"
	@echo "  make report PROJECT=01              # View / generate HTML evolution report"
	@echo "  make profile PROJECT=01             # Analyze shader bottlenecks"
	@echo "  make baseline PROJECT=01            # Capture golden frames & benchmark"
	@echo "  make test                           # Run test suite"

setup: ## Install dependencies, Playwright browser, and verify config.yaml
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating Python virtual environment in $(VENV)..."; \
		if command -v /opt/homebrew/bin/python3.11 >/dev/null 2>&1; then \
			/opt/homebrew/bin/python3.11 -m venv $(VENV); \
		else \
			python3 -m venv $(VENV); \
		fi; \
	fi
	@echo "Upgrading pip and installing dependencies from requirements.txt..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Installing Playwright Chromium browser..."
	$(PLAYWRIGHT) install chromium
	@if [ ! -f config.yaml ]; then \
		echo "⚠️ config.yaml not found! Please check your configuration."; \
	else \
		echo "✅ config.yaml verified."; \
	fi
	@echo "Setup complete! Run 'make auth' then 'make run'."

auth: ## Authenticate with Google Cloud via application-default login
	gcloud auth application-default login

run: ## Run Google Cloud AlphaEvolve optimization loop (use PROJECT=<id> PROGRAMS=<n> SHADER=<file>)
	@mkdir -p artifacts
	$(PYTHON) -m src.run_evolution --project $(PROJECT) --max-programs $(ITERATIONS) $(if $(SHADER),--shader $(SHADER),)

report: ## Generate and view HTML evolution report
	$(PYTHON) -m src.report --project $(PROJECT)

profile: ## Analyze GLSL shader bottlenecks and identify candidate EVOLVE-BLOCK
	$(PYTHON) -m src.run_evolution --project $(PROJECT) --profile-only $(if $(SHADER),--shader $(SHADER),)

baseline: ## Capture golden frames and benchmark seed shader GPU time
	$(PYTHON) -m src.run_evolution --project $(PROJECT) --baseline-only $(if $(SHADER),--shader $(SHADER),)

test: ## Run test suite
	PYTHONPATH=. $(PYTEST) tests/

clean: ## Clean up temporary bytecode and caches
	rm -rf __pycache__ src/__pycache__ src/evaluator_web/__pycache__ .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
