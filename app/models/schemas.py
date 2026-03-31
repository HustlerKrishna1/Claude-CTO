"""
schemas.py — Canonical data models for the Claude CTO System.
All modules share these types. No module defines its own ad-hoc dicts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class TaskStatus(str, Enum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    DONE        = "done"
    FAILED      = "failed"


class TaskPriority(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class ProjectStatus(str, Enum):
    CREATED    = "created"
    PLANNING   = "planning"
    GENERATING = "generating"
    DONE       = "done"
    ARCHIVED   = "archived"


class EventType(str, Enum):
    PROJECT_CREATED = "project_created"
    TASK_STARTED    = "task_started"
    TASK_COMPLETED  = "task_completed"
    FILE_GENERATED  = "file_generated"
    DEBUG_RUN       = "debug_run"
    REFACTOR_RUN    = "refactor_run"
    ERROR           = "error"
    INFO            = "info"


@dataclass
class IdeaParsed:
    project_id:        str
    raw_idea:          str
    problem_statement: str
    features:          List[str]
    target_users:      List[str]
    constraints:       List[str]
    tech_stack:        List[str]
    parsed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "IdeaParsed":
        return cls(**data)


@dataclass
class Task:
    id:           str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id:   str = ""
    title:        str = ""
    description:  str = ""
    priority:     TaskPriority = TaskPriority.MEDIUM
    status:       TaskStatus   = TaskStatus.PENDING
    dependencies: List[str]    = field(default_factory=list)
    file_paths:   List[str]    = field(default_factory=list)
    created_at:   str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at:   str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["priority"] = self.priority.value
        d["status"]   = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        d = data.copy()
        d["priority"] = TaskPriority(d.get("priority", "medium"))
        d["status"]   = TaskStatus(d.get("status", "pending"))
        return cls(**d)


@dataclass
class GeneratedFile:
    path:         str
    content:      str
    language:     str
    task_id:      str = ""
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class DebugResult:
    file_path:       str
    original_error:  str
    root_cause:      str
    fix_description: str
    patched_code:    str
    confidence:      str
    debugged_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class RefactorResult:
    file_path:       str
    original_code:   str
    refactored_code: str
    changes_made:    List[str]
    refactored_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Project:
    id:              str = field(default_factory=lambda: str(uuid.uuid4()))
    name:            str = ""
    raw_idea:        str = ""
    status:          ProjectStatus = ProjectStatus.CREATED
    parsed_idea:     Optional[dict] = None
    tasks:           List[dict]     = field(default_factory=list)
    generated_files: List[str]      = field(default_factory=list)
    project_dir:     str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        d = data.copy()
        d["status"] = ProjectStatus(d.get("status", "created"))
        return cls(**d)


@dataclass
class LogEvent:
    id:         str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    event_type: EventType = EventType.INFO
    message:    str = ""
    metadata:   dict = field(default_factory=dict)
    timestamp:  str  = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["event_type"] = self.event_type.value
        return d
