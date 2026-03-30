# 🧠 Architectural Philosophy

Three core principles govern every design decision:

- **Separation of Concerns** — Each module does exactly one job.  
  The planner doesn't touch files. The generator doesn't call the AI directly. The memory system doesn't know about code.

- **Provider Abstraction** — AI calls are routed through a single AIClient abstraction layer.  
  Swapping from OpenAI to Anthropic to a local model (Ollama) requires changing one config value.

- **Stateful Persistence** — Every project, every task, every decision is recorded.  
  The system can be interrupted and resumed. Nothing is ephemeral.


# 🏗️ System Layers

The system is organized into 4 horizontal layers:

```text
┌─────────────────────────────────────────────────────────┐
│                    CLI INTERFACE LAYER                  │
│         (main.py — Typer-based CLI commands)            │
├─────────────────────────────────────────────────────────┤
│                   ORCHESTRATION LAYER                   │
│      (coordinates modules, manages project state)       │
├──────────────┬──────────────┬───────────────────────────┤
│  PROCESSING  │  PROCESSING  │       PROCESSING          │
│    MODULE    │    MODULE    │        MODULE             │
│ Idea Parser  │   Planner    │  Code Generator           │
│  Debugger    │  Refactor    │  Memory System            │
├──────────────┴──────────────┴───────────────────────────┤
│               INFRASTRUCTURE LAYER                      │
│    AI Client │ File Manager │ SQLite/JSON Storage       │
└─────────────────────────────────────────────────────────┘
```

# ⚙️ Module-by-Module Architecture

## AIClient (Infrastructure)

- Role: Single gateway for all LLM calls  
- Design: Abstract base class + implementations  
- Config-driven via `config.json`  
- All modules call: `ai_client.complete(prompt)`

## IdeaParser (Module)

- Input: Raw idea  
- Output:
  - problem_statement
  - features[]
  - target_users
  - constraints[]  
- Stored in: `projects.json`

## PlannerEngine (Module)

- Input: Parsed idea  
- Output: Task list with dependencies  
- Stored in: SQLite

## CodeGenerator (Module)

- Two-pass:
  1. Structure
  2. Files  
- Output → `generated_projects/`

## FileManager (Infrastructure)

- Handles all file operations  
- Enables testing + abstraction

## Debugger (Module)

- Input: Error + context  
- Output: Fix + patched code  

## RefactorEngine (Module)

- Improves readability, modularity, docs  

## MemorySystem (Module)

- Stores:
  - projects.json
  - logs.json  
- Append-only logging


# 🔄 Data Flow

```text
User Input
   ↓
IdeaParser
   ↓
PlannerEngine
   ↓
CodeGenerator → FileManager
   ↓
MemorySystem

Loop:
User → Debugger / Refactor → Updated files
```

# 💾 Storage

| File | Type | Purpose |
|------|------|--------|
| projects.json | JSON | Metadata |
| logs.json | JSON | Events |
| tasks.db | SQLite | Tasks |
| generated_projects/ | FS | Code |
| config.json | JSON | Config |

# 🎯 Design Decisions

## FastAPI
CLI-first but API-ready.

## JSON + SQLite
- JSON → human-readable  
- SQLite → queryable  

## Two-pass generation
Prevents bad large outputs.

## AI abstraction
Switch providers via config.
