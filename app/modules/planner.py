"""
planner.py — Converts a parsed idea into an ordered, dependency-aware task list.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List

from app.ai_client import AIClientBase, get_ai_client
from app.config import settings
from app.models.schemas import IdeaParsed, Task, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are a senior software architect decomposing a product idea into development tasks.
Return ONLY a valid JSON array. No markdown, no explanation — ONLY the JSON array.
""".strip()


def _build_prompt(parsed: IdeaParsed, max_tasks: int) -> str:
    features_str = "\n".join(f"  - {f}" for f in parsed.features)
    return f"""
Break the following product into a development task list with JSON array of up to {max_tasks} tasks.

PROJECT:
  Problem: {parsed.problem_statement}
  Tech Stack: {', '.join(parsed.tech_stack)}

FEATURES:
{features_str}

Return a JSON array. Each task MUST have:
{{
  "title":        "<Short imperative task title>",
  "description":  "<2-3 sentences of what to implement>",
  "priority":     "<high | medium | low>",
  "dependencies": ["<title of prerequisite task>"]
}}

Rules:
- Start with a setup/init task (no dependencies)
- Use "dependencies" to reference earlier task titles
- Return ONLY the JSON array, nothing else
""".strip()


class PlannerEngine:
    def __init__(self, ai_client: AIClientBase = None):
        self.ai_client = ai_client or get_ai_client()
        self.max_tasks = settings.planner.max_tasks

    def plan(self, parsed: IdeaParsed) -> List[Task]:
        logger.info("Planning tasks for %s...", parsed.project_id)

        try:
            raw_tasks = self.ai_client.complete_json(
                _build_prompt(parsed, self.max_tasks), system=_SYSTEM_PROMPT
            )
        except Exception as e:
            raise RuntimeError(f"PlannerEngine: AI call failed — {e}") from e

        if not isinstance(raw_tasks, list):
            raise ValueError(
                f"PlannerEngine: expected JSON array, got {type(raw_tasks).__name__}"
            )

        tasks = self._parse_raw(raw_tasks, parsed.project_id)
        tasks = self._resolve_deps(tasks)
        tasks = self._topo_sort(tasks)
        logger.info("Plan complete: %d tasks", len(tasks))
        return tasks

    def _parse_raw(self, raw: list, project_id: str) -> List[Task]:
        tasks = []
        for i, r in enumerate(raw):
            if not isinstance(r, dict):
                continue
            title = str(r.get("title", f"Task {i+1}")).strip() or f"Task {i+1}"
            try:
                priority = TaskPriority(str(r.get("priority", "medium")).lower())
            except ValueError:
                priority = TaskPriority.MEDIUM
            task = Task(
                id          = str(uuid.uuid4()),
                project_id  = project_id,
                title       = title,
                description = str(r.get("description", "")).strip(),
                priority    = priority,
                status      = TaskStatus.PENDING,
                dependencies = [],
            )
            task._dep_titles = [str(d).strip() for d in r.get("dependencies", [])]
            tasks.append(task)
        return tasks

    def _resolve_deps(self, tasks: List[Task]) -> List[Task]:
        title_map = {t.title.lower(): t.id for t in tasks}
        for task in tasks:
            task.dependencies = [
                title_map[d.lower()]
                for d in getattr(task, "_dep_titles", [])
                if d.lower() in title_map
            ]
            if hasattr(task, "_dep_titles"):
                del task._dep_titles
        return tasks

    def _topo_sort(self, tasks: List[Task]) -> List[Task]:
        id_map     = {t.id: t for t in tasks}
        in_degree  = {t.id: 0 for t in tasks}
        dependents: Dict[str, List[str]] = {t.id: [] for t in tasks}

        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id in id_map:
                    in_degree[task.id] += 1
                    dependents[dep_id].append(task.id)

        queue    = [tid for tid, deg in in_degree.items() if deg == 0]
        ordered  = []

        while queue:
            queue.sort(key=lambda tid: {"high": 0, "medium": 1, "low": 2}.get(
                id_map[tid].priority.value, 1))
            tid = queue.pop(0)
            ordered.append(tid)
            for dep_id in dependents[tid]:
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)

        remaining = [tid for tid in id_map if tid not in ordered]
        if remaining:
            logger.warning("Cycle detected — appending %d tasks at end", len(remaining))
            ordered.extend(remaining)

        return [id_map[tid] for tid in ordered if tid in id_map]

    def display(self, tasks: List[Task]) -> str:
        lines = ["=" * 60, f"📋  TASK PLAN  ({len(tasks)} tasks)", "=" * 60]
        icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        for i, t in enumerate(tasks, 1):
            lines.append(
                f"\n{i}. {icons.get(t.priority.value,'⚪')} "
                f"[{t.priority.value.upper()}] {t.title}"
            )
            lines.append(f"   {t.description}")
            if t.dependencies:
                dep_titles = [x.title for x in tasks if x.id in t.dependencies]
                lines.append(f"   Depends on: {', '.join(dep_titles)}")
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)
