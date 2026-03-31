"""
idea_parser.py — Converts a raw idea string into a structured IdeaParsed object.
"""

from __future__ import annotations

import logging
import uuid
from typing import List

from app.ai_client import AIClientBase, get_ai_client
from app.models.schemas import IdeaParsed

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are a senior software architect and product analyst.
Analyse a raw product idea and extract structured information.
Always respond with ONLY a valid JSON object — no markdown fences, no extra text.
""".strip()


def _build_prompt(raw_idea: str) -> str:
    return f"""
Analyse the following product idea and return a structured JSON object.

IDEA:
\"\"\"{raw_idea}\"\"\"

Return EXACTLY this JSON structure (no extra keys, no markdown):
{{
  "problem_statement": "<One concise sentence describing the core problem>",
  "features": ["<Feature 1>", "<Feature 2>", "<Feature 3>"],
  "target_users": ["<User type 1>", "<User type 2>"],
  "constraints": ["<Constraint 1>"],
  "tech_stack": ["<Technology 1>", "<Technology 2>"]
}}

Rules:
- problem_statement: ONE sentence
- features: at least 3, at most 10
- target_users: at least 1, at most 5
- tech_stack: practical production-ready choices
- Return ONLY the JSON, nothing else
""".strip()


class IdeaParser:
    def __init__(self, ai_client: AIClientBase = None):
        self.ai_client = ai_client or get_ai_client()

    def parse(self, raw_idea: str, project_id: str = None) -> IdeaParsed:
        if not raw_idea or not raw_idea.strip():
            raise ValueError("raw_idea cannot be empty")

        raw_idea   = raw_idea.strip()
        project_id = project_id or str(uuid.uuid4())
        logger.info("Parsing idea for project %s...", project_id)

        try:
            data = self.ai_client.complete_json(_build_prompt(raw_idea), system=_SYSTEM_PROMPT)
        except Exception as e:
            raise RuntimeError(f"IdeaParser: AI call failed — {e}") from e

        result = IdeaParsed(
            project_id        = project_id,
            raw_idea          = raw_idea,
            problem_statement = _req_str(data, "problem_statement"),
            features          = _req_list(data, "features", min_length=1),
            target_users      = _req_list(data, "target_users", min_length=1),
            constraints       = data.get("constraints", []),
            tech_stack        = _req_list(data, "tech_stack", min_length=1),
        )
        logger.info("Idea parsed: %s", result.problem_statement[:60])
        return result

    def display(self, parsed: IdeaParsed) -> str:
        lines = [
            "=" * 60, "📋  PARSED IDEA", "=" * 60,
            f"\n🎯  Problem Statement:\n    {parsed.problem_statement}",
            f"\n🔧  Tech Stack:\n    {', '.join(parsed.tech_stack)}",
            "\n✅  Features:",
        ]
        for i, f in enumerate(parsed.features, 1):
            lines.append(f"    {i}. {f}")
        lines.append("\n👥  Target Users:")
        for u in parsed.target_users:
            lines.append(f"    • {u}")
        if parsed.constraints:
            lines.append("\n⚠️   Constraints:")
            for c in parsed.constraints:
                lines.append(f"    • {c}")
        lines.append("=" * 60)
        return "\n".join(lines)


def _req_str(data: dict, key: str) -> str:
    val = data.get(key, "")
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"IdeaParser: expected non-empty string for '{key}'")
    return val.strip()


def _req_list(data: dict, key: str, min_length: int = 0) -> List[str]:
    val = data.get(key, [])
    if not isinstance(val, list):
        raise ValueError(f"IdeaParser: expected list for '{key}'")
    result = [str(i).strip() for i in val if str(i).strip()]
    if len(result) < min_length:
        raise ValueError(f"IdeaParser: '{key}' needs at least {min_length} item(s)")
    return result
