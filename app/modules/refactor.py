"""
refactor.py — AI-powered code refactoring engine.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from app.ai_client import AIClientBase, get_ai_client
from app.models.schemas import RefactorResult
from app.modules.file_manager import FileManager

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are a senior software engineer performing a code review and refactor.
Focus on clean code: readability, modularity, and maintainability.
Return ONLY a valid JSON object — no markdown fences, no preamble.
""".strip()


def _build_prompt(file_path: str, content: str, language: str,
                  focus: Optional[List[str]]) -> str:
    focus_str = (
        "\n".join(f"  - {a}" for a in focus) if focus
        else "  - All areas: readability, modularity, error handling, documentation"
    )
    return f"""
Refactor the following {language} file: {file_path}

CONTENT:
```
{content}
```

FOCUS:
{focus_str}

Guidelines:
- Improve names, break long functions, add docstrings, add type hints (Python)
- Improve error handling, remove dead code and magic numbers
- Preserve ALL existing functionality
- Do NOT add new features

Return EXACTLY this JSON:
{{
  "refactored_code": "<Complete refactored file — ALL lines>",
  "changes_made": ["<Change 1>", "<Change 2>"]
}}

Return ONLY the JSON.
""".strip()


class RefactorEngine:
    def __init__(self, file_manager: FileManager, ai_client: AIClientBase = None):
        self.ai_client    = ai_client or get_ai_client()
        self.file_manager = file_manager

    def refactor_file(self, file_path: str, project_name: str,
                      focus_areas: Optional[List[str]] = None,
                      auto_apply: bool = True) -> RefactorResult:
        try:
            original = self.file_manager.read_file(file_path, project_name)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Cannot refactor: '{file_path}' not found in '{project_name}'"
            )

        result = self._run(file_path, original, _detect_language(file_path), focus_areas)

        if auto_apply and result.refactored_code:
            self.file_manager.write_file(file_path, result.refactored_code, project_name)
            logger.info("Refactored '%s' (%d changes)", file_path, len(result.changes_made))

        return result

    def refactor_project(self, project_name: str,
                         extensions: Optional[List[str]] = None,
                         focus_areas: Optional[List[str]] = None) -> List[RefactorResult]:
        default_ext = {".py", ".js", ".ts", ".java", ".go", ".rb", ".php"}
        target      = set(extensions) if extensions else default_ext
        files       = [f for f in self.file_manager.list_files(project_name)
                       if any(f.endswith(e) for e in target)]
        results = []
        for fp in files:
            try:
                results.append(self.refactor_file(fp, project_name, focus_areas))
            except Exception as e:
                logger.error("Failed to refactor '%s': %s", fp, e)
        return results

    def refactor_from_string(self, file_path: str, content: str,
                             focus_areas: Optional[List[str]] = None) -> RefactorResult:
        return self._run(file_path, content, _detect_language(file_path), focus_areas)

    def _run(self, file_path: str, original: str, language: str,
             focus: Optional[List[str]]) -> RefactorResult:
        try:
            parsed = self.ai_client.complete_json(
                _build_prompt(file_path, original, language, focus), system=_SYSTEM_PROMPT
            )
        except Exception as e:
            raise RuntimeError(f"RefactorEngine: AI call failed — {e}") from e

        refactored  = str(parsed.get("refactored_code", original)).strip()
        changes_raw = parsed.get("changes_made", [])
        changes     = [str(c).strip() for c in (changes_raw if isinstance(changes_raw, list)
                       else [str(changes_raw)]) if str(c).strip()]
        return RefactorResult(
            file_path       = file_path,
            original_code   = original,
            refactored_code = refactored,
            changes_made    = changes or ["No significant changes needed."],
        )

    def display(self, result: RefactorResult) -> str:
        orig_lines = len(result.original_code.splitlines())
        new_lines  = len(result.refactored_code.splitlines())
        delta      = new_lines - orig_lines
        return "\n".join([
            "=" * 60, "♻️   REFACTOR RESULT", "=" * 60,
            f"\n📁  File: {result.file_path}",
            f"\n✅  Changes ({len(result.changes_made)}):",
            *[f"    {i}. {c}" for i, c in enumerate(result.changes_made, 1)],
            f"\n📊  Lines: {orig_lines} → {new_lines} ({'+' if delta >= 0 else ''}{delta})",
            "=" * 60,
        ])


def _detect_language(file_path: str) -> str:
    ext_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".java": "Java", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
        ".php": "PHP", ".c": "C", ".cpp": "C++", ".cs": "C#", ".sh": "Bash",
    }
    return ext_map.get(Path(file_path).suffix.lower(), "code")
