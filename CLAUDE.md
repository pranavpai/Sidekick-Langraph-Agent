# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a LangGraph-based AI agent system called "Sidekick" that autonomously completes complex tasks using various tools and evaluates its work against user-defined success criteria.

## Architecture

The system consists of three main components:

1. **Sidekick Agent** (`sidekick.py`): The core LangGraph agent with a worker-evaluator pattern
   - Worker node: Executes tasks using available tools
   - Evaluator node: Assesses completion against success criteria
   - Tools node: Handles tool execution via LangChain ToolNode

2. **Tools** (`sidekick_tools.py`): Provides various capabilities
   - Playwright browser automation (non-headless)
   - File management (in `sandbox/` directory)
   - Web search via Google Serper API
   - Python REPL execution
   - Wikipedia queries
   - Push notifications via Pushover

3. **Gradio Interface** (`app.py`): Web UI for user interaction
   - Message input and success criteria specification
   - Chat history display
   - Reset functionality

## Key Implementation Details

- Uses OpenAI GPT-4o-mini for both worker and evaluator LLMs
- State management via LangGraph State with message history
- Memory persistence through MemorySaver checkpointer
- Evaluation loop continues until success criteria met or user input needed
- Browser resources are managed with proper cleanup in `free_resources()`

## Environment Setup

Required environment variables:
- `OPENAI_API_KEY`: OpenAI API access
- `SERPER_API_KEY`: Google Serper API for web search
- `PUSHOVER_TOKEN` and `PUSHOVER_USER`: Push notification service

## Common Commands

Run the application:
```bash
python app.py
```

Install dependencies:
```bash
pip install -e .
```

## Python Coding Standards

### Formatting & Quality
- Use Black formatter (88 chars, double quotes)
- Run `black .` before committing
- All code must pass `ruff check .` and `mypy .`
- Use type hints for functions and methods
- Include docstrings for public functions/classes

### Commands
- Format: `black .`
- Lint: `ruff check .`
- Type check: `mypy .`
- Install dev tools: `pip install black ruff mypy pre-commit`

## Development Notes

- The `sandbox/` directory is used for file operations to contain tool file access
- Browser automation runs in non-headless mode for debugging
- The agent supports a recursion limit of 50 for complex task loops
- All async operations are properly handled throughout the codebase