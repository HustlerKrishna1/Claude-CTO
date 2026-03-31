"""
debugger.py — AI-powered code debugger. Analyses errors and produces patches.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.ai_client import AIClientBase, get_ai_client
from app.models.schemas import DebugResult
from app.modules.file_manager import FileManager

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are an expert software debugger. Reason carefully about errors, identify root causes,
and produce minimal clean fixes. Return ONLY a valid JSON object — no markdown, no explanation.
""".strip()


def _build_prompt(file_path: str, error: str, content: str, context: Optional[str]) -> str:
    ctx = f"\nADDITIONAL CONTEXT:\n{context}" if context else ""
    return f"""
Debug the following error in file: {file_path}

ERROR:
{error}

FILE CONTENT:
```
{content}
```
{ctx}

Return EXACTLY this JSON:
{{
  "root_cause":      "<One sentence explaining the root cause>",
  "fix_description": "<2-3 sentences explaining the fix>",
  "patched_code":    "<The COMPLETE fixed file — all lines, not just changed ones>",
  "confidence":      "<high | medium | low>"
}}

Rules:
- patched_code must be the ENTIRE file
- Make the minimal fix only
- Return ONLY the JSON
""".strip()


class Debugger:
    def __init__(self, file_manager: FileManager, ai_client: AIClientBase = None):
        self.ai_client    = ai_client or get_ai_client()
        self.file_manager = file_manager

    def debug(self, file_path: str, error_message: str, project_name: str,
              context: Optional[str] = None, auto_apply: bool = True) -> DebugResult:
        try:
            content = self.file_manager.read_file(file_path, project_name)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Cannot debug: '{file_path}' not found in project '{project_name}'"
            )

        result = self._run(file_path, error_message, content, context)

        if auto_apply and result.patched_code:
            self.file_manager.write_file(file_path, result.patched_code, project_name)
            logger.info("Patch applied to '%s' (confidence: %s)", file_path, result.confidence)

        return result

    def debug_from_string(self, file_path: str, error_message: str,
                          file_content: str, context: Optional[str] = None) -> DebugResult:
        return self._run(file_path, error_message, file_content, context)

    def _run(self, file_path: str, error: str, content: str,
             context: Optional[str]) -> DebugResult:
        try:
            parsed = self.ai_client.complete_json(
                _build_prompt(file_path, error, content, context), system=_SYSTEM_PROMPT
            )
        except Exception as e:
            raise RuntimeError(f"Debugger: AI call failed — {e}") from e

        confidence = str(parsed.get("confidence", "medium")).lower()
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"

        return DebugResult(
            file_path       = file_path,
            original_error  = error,
            root_cause      = str(parsed.get("root_cause", "Unknown")).strip(),
            fix_description = str(parsed.get("fix_description", "")).strip(),
            patched_code    = str(parsed.get("patched_code", content)).strip(),
            confidence      = confidence,
        )

    def display(self, result: DebugResult) -> str:
        icons = {"high": "✅", "medium": "⚠️ ", "low": "❓"}
        return "\n".join([
            "=" * 60, "🐛  DEBUG RESULT", "=" * 60,
            f"\n📁  File:      {result.file_path}",
            f"🔍  Error:     {result.original_error[:120]}",
            f"\n🎯  Root Cause:\n    {result.root_cause}",
            f"\n🔧  Fix:\n    {result.fix_description}",
            f"\n{icons.get(result.confidence,'⚠️ ')} Confidence: {result.confidence.upper()}",
            "=" * 60,
        ])
