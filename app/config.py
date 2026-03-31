"""
config.py — Loads and validates system configuration from config.json.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

ROOT_DIR    = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"


@dataclass
class AIConfig:
    provider:        str
    model:           str
    temperature:     float
    max_tokens:      int
    api_key_env:     str
    timeout_seconds: int

    @property
    def api_key(self) -> Optional[str]:
        """Return API key from env, or None if not required (e.g. Ollama)."""
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env)


@dataclass
class StorageConfig:
    projects_file: str
    logs_file:     str
    generated_dir: str

    @property
    def projects_path(self) -> Path:
        return ROOT_DIR / self.projects_file

    @property
    def logs_path(self) -> Path:
        return ROOT_DIR / self.logs_file

    @property
    def generated_path(self) -> Path:
        return ROOT_DIR / self.generated_dir


@dataclass
class PlannerConfig:
    max_tasks:        int
    default_priority: str


@dataclass
class GeneratorConfig:
    max_files_per_task: int
    include_comments:   bool
    include_tests:      bool


@dataclass
class LoggingConfig:
    level:           str
    show_ai_prompts: bool


@dataclass
class Settings:
    ai:        AIConfig
    storage:   StorageConfig
    planner:   PlannerConfig
    generator: GeneratorConfig
    logging:   LoggingConfig
    providers: Dict[str, dict]


def _load_settings() -> Settings:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"config.json not found at {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    ai_raw = raw["ai"]
    ai = AIConfig(
        provider        = ai_raw["provider"],
        model           = ai_raw["model"],
        temperature     = float(ai_raw["temperature"]),
        max_tokens      = int(ai_raw["max_tokens"]),
        api_key_env     = ai_raw.get("api_key_env", ""),
        timeout_seconds = int(ai_raw["timeout_seconds"]),
    )

    s = raw["storage"]
    storage = StorageConfig(
        projects_file = s["projects_file"],
        logs_file     = s["logs_file"],
        generated_dir = s["generated_dir"],
    )

    p = raw["planner"]
    planner = PlannerConfig(
        max_tasks        = int(p["max_tasks"]),
        default_priority = p["default_priority"],
    )

    g = raw["generator"]
    generator = GeneratorConfig(
        max_files_per_task = int(g["max_files_per_task"]),
        include_comments   = bool(g["include_comments"]),
        include_tests      = bool(g["include_tests"]),
    )

    l = raw.get("logging", {})
    logging_cfg = LoggingConfig(
        level           = l.get("level", "INFO"),
        show_ai_prompts = bool(l.get("show_ai_prompts", False)),
    )

    return Settings(
        ai        = ai,
        storage   = storage,
        planner   = planner,
        generator = generator,
        logging   = logging_cfg,
        providers = raw.get("providers", {}),
    )


settings: Settings = _load_settings()
