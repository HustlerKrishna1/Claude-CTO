"""
file_manager.py — All file system I/O for the Claude CTO System.
No other module may call open() or os.makedirs() directly.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import List

from app.config import settings

logger = logging.getLogger(__name__)


class FileManager:
    """Handles all read/write/delete operations for generated project files."""

    def __init__(self, dry_run: bool = False):
        self.dry_run   = dry_run
        self.base_path = settings.storage.generated_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def create_project_dir(self, project_name: str) -> Path:
        proj_dir = self.base_path / _slugify(project_name)
        if not self.dry_run:
            proj_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Created project directory: %s", proj_dir)
        return proj_dir

    def write_file(self, relative_path: str, content: str, project_name: str) -> Path:
        full_path = self.base_path / _slugify(project_name) / relative_path
        if self.dry_run:
            logger.info("[DRY-RUN] Would write %d chars → %s", len(content), full_path)
            return full_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Written: %s", full_path)
        return full_path

    def read_file(self, relative_path: str, project_name: str) -> str:
        full_path = self.base_path / _slugify(project_name) / relative_path
        if not full_path.exists():
            raise FileNotFoundError(
                f"File not found in project '{project_name}': {relative_path}"
            )
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    def list_files(self, project_name: str) -> List[str]:
        proj_dir = self.base_path / _slugify(project_name)
        if not proj_dir.exists():
            return []
        return sorted(
            str(p.relative_to(proj_dir))
            for p in proj_dir.rglob("*") if p.is_file()
        )

    def list_projects(self) -> List[str]:
        return sorted(d.name for d in self.base_path.iterdir() if d.is_dir()) \
            if self.base_path.exists() else []

    def project_exists(self, project_name: str) -> bool:
        return (self.base_path / _slugify(project_name)).exists()

    def get_project_path(self, project_name: str) -> Path:
        return self.base_path / _slugify(project_name)

    def delete_project(self, project_name: str) -> bool:
        proj_dir = self.base_path / _slugify(project_name)
        if not proj_dir.exists():
            return False
        if self.dry_run:
            logger.info("[DRY-RUN] Would delete: %s", proj_dir)
            return True
        try:
            shutil.rmtree(proj_dir)
        except PermissionError as e:
            raise PermissionError(f"Permission denied deleting {proj_dir}") from e
        logger.info("Deleted: %s", proj_dir)
        return True

    def print_tree(self, project_name: str) -> str:
        proj_dir = self.base_path / _slugify(project_name)
        if not proj_dir.exists():
            return f"[Project '{project_name}' not found]"
        lines = [f"{_slugify(project_name)}/"]
        for path in sorted(proj_dir.rglob("*")):
            rel   = path.relative_to(proj_dir)
            depth = len(rel.parts) - 1
            lines.append("    " * depth + "├── " + rel.parts[-1])
        return "\n".join(lines)


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug.strip("_") or "unnamed_project"
