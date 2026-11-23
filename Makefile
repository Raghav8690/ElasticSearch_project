.DEFAULT_GOAL := help

VENV ?= .venv
PYTHON ?= python
HOST ?= 127.0.0.1
PORT ?= 8000

ifeq ($(OS),Windows_NT)
VENV_PY := $(VENV)/Scripts/python.exe
BLANK := echo.
else
VENV_PY := $(VENV)/bin/python
BLANK := echo
endif

PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),$(PYTHON))
UVICORN := $(PY) -m uvicorn

.PHONY: help install backend frontend both run dev check clean

help:
	@echo Gujrat RERA Explorer
	@$(BLANK)
	@echo Targets:
	@echo   make install   Create venv and install Python dependencies
	@echo   make backend   Run FastAPI backend at http://$(HOST):$(PORT)
	@echo   make frontend  Serve the UI (backend serves the static files)
	@echo   make both      Single command for backend + frontend (recommended)
	@echo   make run       Alias for both
	@echo   make dev       Alias for both
	@echo   make check     Run backend compile and frontend syntax checks
	@echo   make clean     Remove Python caches
	@$(BLANK)
	@echo Overrides: make both PORT=9000 HOST=0.0.0.0

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r requirements.txt

backend:
	@echo Starting Gujrat RERA Explorer at http://$(HOST):$(PORT)
	$(UVICORN) backend.main:app --reload --host $(HOST) --port $(PORT)

frontend: backend

both: backend

run: both

dev: both

check:
	$(PY) -m compileall -q backend
	node --check frontend/app.js

clean:
	$(PY) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
