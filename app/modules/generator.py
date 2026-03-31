"""
generator.py — Two-pass code generator. Pass 1: file structure. Pass 2: file content.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from app.ai_client import AIClientBase, get_ai_client
from app.config import settings
from app.models.schemas import GeneratedFile, IdeaParsed, Task
from app.modules.file_manager import FileManager

logger = logging.getLogger(__name__)

_STRUCTURE_SYSTEM = "You are a senior engineer planning file structure. Return ONLY a valid JSON array of file path strings."
_CODE_SYSTEM      = "You are a senior engineer writing production-quality code. Return ONLY raw file content — no markdown fences."


class CodeGenerator:
    def __init__(self, file_manager: FileManager, ai_client: AIClientBase = None):
        self.ai_client    = ai_client or get_ai_client()
        self.file_manager = file_manager

    def generate_for_task(self, task: Task, parsed: IdeaParsed, project_name: str) -> List[GeneratedFile]:
        logger.info("Generating code for task: %s", task.title)
        file_paths = self._get_structure(task, parsed)
        if not file_paths:
            logger.warning("No files to generate for task: %s", task.title)
            return []

        generated = []
        for fp in file_paths:
            gf = self._generate_file(task, parsed, fp, file_paths, project_name)
            if gf:
                generated.append(gf)

        logger.info("Task '%s': %d files generated", task.title, len(generated))
        return generated

    def generate_project_readme(self, parsed: IdeaParsed, tasks: list, project_name: str) -> GeneratedFile:
        task_list = "\n".join(f"- [{t.status.value.upper()}] {t.title}" for t in tasks)
        prompt = f"""
Write a professional README.md for:
Project: {project_name}
Problem: {parsed.problem_statement}
Tech Stack: {', '.join(parsed.tech_stack)}
Features: {', '.join(parsed.features)}
Tasks: {task_list}
Include: title, description, features, tech stack, install steps, usage, project structure.
Return ONLY raw markdown.
""".strip()
        content = self.ai_client.complete(prompt, system=_CODE_SYSTEM)
        self.file_manager.write_file("README.md", content, project_name)
        return GeneratedFile(path="README.md", content=content, language="markdown")

    def _get_structure(self, task: Task, parsed: IdeaParsed) -> List[str]:
        prompt = f"""
You are implementing this task:
  Task: {task.title} — {task.description}
  Project: {parsed.problem_statement}
  Tech Stack: {', '.join(parsed.tech_stack)}

List the files that need to be created for this task.
Return a JSON array of relative file paths (e.g. ["src/main.py", "src/utils.py"]).
Include at most {settings.generator.max_files_per_task} files.
Return ONLY the JSON array.
""".strip()
        try:
            raw = self.ai_client.complete_json(prompt, system=_STRUCTURE_SYSTEM)
        except Exception as e:
            logger.error("Structure generation failed for '%s': %s", task.title, e)
            return []

        if not isinstance(raw, list):
            return []

        return [
            str(item).strip().lstrip("/")
            for item in raw
            if str(item).strip() and ".." not in str(item)
        ][:settings.generator.max_files_per_task]

    def _generate_file(self, task: Task, parsed: IdeaParsed, file_path: str,
                       all_files: List[str], project_name: str) -> Optional[GeneratedFile]:
        others     = [f for f in all_files if f != file_path]
        ctx_str    = "\n".join(f"  - {f}" for f in others[:10]) or "  (only file)"
        comment_rule = "Include docstrings and inline comments." \
            if settings.generator.include_comments else "Keep comments minimal."

        prompt = f"""
Write the complete contents of the file: {file_path}

PROJECT: {parsed.problem_statement}
TECH STACK: {', '.join(parsed.tech_stack)}
TASK: {task.title} — {task.description}
OTHER FILES IN THIS TASK:
{ctx_str}

Requirements:
- Production-ready, working code
- Handle errors and edge cases
- {comment_rule}
- Return ONLY the raw file content — no markdown fences, no explanation
""".strip()

        try:
            content = self.ai_client.complete(prompt, system=_CODE_SYSTEM)
        except Exception as e:
            logger.error("Code generation failed for '%s': %s", file_path, e)
            return None

        if not content.strip():
            return None

        self.file_manager.write_file(file_path, content, project_name)
        return GeneratedFile(
            path     = file_path,
            content  = content,
            language = _detect_language(file_path),
            task_id  = task.id,
        )


def _detect_language(file_path: str) -> str:
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx", ".tsx": "tsx", ".html": "html", ".css": "css",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".md": "markdown",
        ".sh": "bash", ".sql": "sql", ".go": "go", ".rs": "rust",
        ".java": "java", ".rb": "ruby", ".php": "php", ".toml": "toml",
    }
    return ext_map.get(Path(file_path).suffix.lower(), "text")
