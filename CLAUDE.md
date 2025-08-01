# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python project called "Streaming" set up with a virtual environment.

## Development Setup

- Virtual environment is located in `.venv/`
- Activate the virtual environment before development:
  - Windows: `.venv\Scripts\activate`
  - Unix/macOS: `source .venv/bin/activate`

## Common Commands

### Environment Management
```bash
# Activate virtual environment (Windows)
.venv\Scripts\activate

# Activate virtual environment (Unix/macOS)  
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Generate requirements file
pip freeze > requirements.txt
```

### Development Commands
```bash
# Run the main application (when main.py exists)
python main.py

# Run tests (when test files exist)
python -m pytest

# Run a specific test file
python -m pytest tests/test_filename.py

# Run with coverage
python -m pytest --cov=src

# Format code (if black is installed)
black .

# Lint code (if flake8 is installed)
flake8 .

# Type checking (if mypy is installed)
mypy .
```

## Project Structure

Currently the project structure is minimal with only the virtual environment set up. The structure will grow as the project develops.