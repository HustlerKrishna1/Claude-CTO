"""
memory.py — Persistent memory system. Stores projects (JSON) and event logs (JSON).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.config import settings
from app.models.schemas import EventType, LogEvent, Project, ProjectStatus

logger = logging.getLogger(__name__)


class MemorySystem:
    def __init__(self):
        self._projects_path: Path = settings.storage.projects_path
        self._logs_path:     Path = settings.storage.logs_path
        self._init_storage()

    def _init_storage(self) -> None:
        for path, default in [(self._projects_path, {}), (self._logs_path, [])]:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(default, f, indent=2)

    # --- Projects ---

    def save_project(self, project: Project) -> None:
        projects = self._load_projects_raw()
        project.updated_at = datetime.utcnow().isoformat()
        projects[project.id] = project.to_dict()
        self._write_projects(projects)

    def load_project(self, project_id: str) -> Optional[Project]:
        data = self._load_projects_raw().get(project_id)
        return Project.from_dict(data) if data else None

    def load_project_by_name(self, name: str) -> Optional[Project]:
        matches = [
            Project.from_dict(v)
            for v in self._load_projects_raw().values()
            if v.get("name", "").lower() == name.lower()
        ]
        return sorted(matches, key=lambda p: p.updated_at, reverse=True)[0] \
            if matches else None

    def list_projects(self) -> List[Project]:
        return sorted(
            [Project.from_dict(v) for v in self._load_projects_raw().values()],
            key=lambda p: p.updated_at, reverse=True,
        )

    def delete_project(self, project_id: str) -> bool:
        projects = self._load_projects_raw()
        if project_id not in projects:
            return False
        del projects[project_id]
        self._write_projects(projects)
        return True

    def update_project_status(self, project_id: str, status: ProjectStatus) -> None:
        project = self.load_project(project_id)
        if project:
            project.status = status
            self.save_project(project)

    # --- Event log ---

    def log_event(self, project_id: str, event_type: EventType,
                  message: str, metadata: Optional[dict] = None) -> LogEvent:
        event = LogEvent(project_id=project_id, event_type=event_type,
                         message=message, metadata=metadata or {})
        logs = self._load_logs_raw()
        logs.append(event.to_dict())
        self._write_logs(logs)
        return event

    def get_events(self, project_id: Optional[str] = None,
                   event_type: Optional[EventType] = None,
                   limit: int = 100) -> List[LogEvent]:
        events = []
        for entry in reversed(self._load_logs_raw()):
            if project_id and entry.get("project_id") != project_id:
                continue
            if event_type and entry.get("event_type") != event_type.value:
                continue
            events.append(LogEvent(
                id         = entry.get("id", ""),
                project_id = entry.get("project_id", ""),
                event_type = EventType(entry.get("event_type", "info")),
                message    = entry.get("message", ""),
                metadata   = entry.get("metadata", {}),
                timestamp  = entry.get("timestamp", ""),
            ))
            if len(events) >= limit:
                break
        return events

    def get_project_history(self, project_id: str) -> List[LogEvent]:
        return list(reversed(self.get_events(project_id=project_id, limit=1000)))

    def get_stats(self) -> dict:
        projects = self._load_projects_raw()
        logs     = self._load_logs_raw()
        counts: Dict[str, int] = {}
        for p in projects.values():
            s = p.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        return {"total_projects": len(projects), "total_events": len(logs),
                "projects_by_status": counts}

    # --- I/O ---

    def _load_projects_raw(self) -> Dict[str, dict]:
        try:
            with open(self._projects_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_projects(self, data: Dict[str, dict]) -> None:
        with open(self._projects_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_logs_raw(self) -> List[dict]:
        try:
            with open(self._logs_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_logs(self, data: List[dict]) -> None:
        with open(self._logs_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
