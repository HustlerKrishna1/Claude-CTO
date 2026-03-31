"""
main.py — CLI entry point for the Claude CTO System.
Powered by Ollama (local AI — no API key needed).

Commands: new | generate | debug | refactor | list | status | history
Run: python -m app.main --help
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

from app.config import settings
from app.models.schemas import EventType, ProjectStatus, TaskStatus
from app.modules.file_manager import FileManager
from app.modules.memory import MemorySystem
from app.modules.idea_parser import IdeaParser
from app.modules.planner import PlannerEngine
from app.modules.generator import CodeGenerator
from app.modules.debugger import Debugger
from app.modules.refactor import RefactorEngine

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level   = getattr(logging, settings.logging.level, logging.INFO),
    format  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt = "%H:%M:%S",
    stream  = sys.stderr,
)

app     = typer.Typer(
    name             = "claude-cto",
    help             = "🤖  Claude CTO — AI-powered dev assistant (powered by Ollama)",
    add_completion   = False,
    rich_markup_mode = "rich",
)
console = Console()


def _modules():
    fm  = FileManager()
    mem = MemorySystem()
    return (
        fm, mem,
        IdeaParser(),
        PlannerEngine(),
        CodeGenerator(file_manager=fm),
        Debugger(file_manager=fm),
        RefactorEngine(file_manager=fm),
    )


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

@app.command()
def new(
    idea: Optional[str] = typer.Argument(None, help="Product idea text. Prompted if omitted."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name."),
    skip_generate: bool = typer.Option(False, "--plan-only", help="Stop after planning."),
    dry_run:       bool = typer.Option(False, "--dry-run",   help="Plan without writing files."),
):
    """🚀  New project: idea → plan → generate code."""
    rprint(Panel.fit(
        f"[bold cyan]Claude CTO[/bold cyan]  •  Ollama [{settings.ai.model}]",
        border_style="cyan",
    ))

    if not idea:
        idea = typer.prompt("\n💡 Describe your product idea")
    if not idea.strip():
        rprint("[red]Error:[/red] Idea cannot be empty.")
        raise typer.Exit(1)

    fm, mem, idea_parser, planner, generator, _, _ = _modules()
    if dry_run:
        fm.dry_run = True

    # Parse
    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}"), console=console) as p:
        t = p.add_task("Parsing idea...", total=None)
        try:
            parsed = idea_parser.parse(idea)
        except Exception as e:
            rprint(f"[red]Parse failed:[/red] {e}")
            raise typer.Exit(1)
        p.update(t, description="✅ Idea parsed")

    rprint(idea_parser.display(parsed))

    project_name = name or _idea_to_name(idea)
    rprint(f"\n📁  Project: [bold]{project_name}[/bold]")

    from app.models.schemas import Project
    project = Project(
        id          = parsed.project_id,
        name        = project_name,
        raw_idea    = idea,
        status      = ProjectStatus.PLANNING,
        parsed_idea = parsed.to_dict(),
    )
    mem.save_project(project)
    mem.log_event(project.id, EventType.PROJECT_CREATED, f"New project: {project_name}")

    # Plan
    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}"), console=console) as p:
        t = p.add_task("Planning tasks...", total=None)
        try:
            tasks = planner.plan(parsed)
        except Exception as e:
            rprint(f"[red]Planning failed:[/red] {e}")
            raise typer.Exit(1)
        p.update(t, description="✅ Tasks planned")

    rprint(planner.display(tasks))

    project.tasks  = [t.to_dict() for t in tasks]
    project.status = ProjectStatus.GENERATING
    mem.save_project(project)

    if skip_generate:
        rprint(f"\n[yellow]--plan-only: stopping before code generation.[/yellow]")
        rprint(f"✅  Project ID: [bold]{project.id}[/bold]")
        return

    # Generate
    rprint("\n[bold cyan]⚙️  Generating code...[/bold cyan]")
    all_files = []

    for i, task_obj in enumerate(tasks, 1):
        rprint(f"\n  [{i}/{len(tasks)}] {task_obj.title}")
        with Progress(SpinnerColumn(), TextColumn("    [dim]{task.description}"), console=console) as p:
            gt = p.add_task("Generating...", total=None)
            try:
                gen_files      = generator.generate_for_task(task_obj, parsed, project_name)
                all_files.extend(gen_files)
                task_obj.status = TaskStatus.DONE
                mem.log_event(project.id, EventType.TASK_COMPLETED,
                              f"Task done: {task_obj.title}",
                              {"files": [f.path for f in gen_files]})
                p.update(gt, description=f"✅ {len(gen_files)} file(s)")
            except Exception as e:
                task_obj.status = TaskStatus.FAILED
                p.update(gt, description=f"❌ {e}")
                mem.log_event(project.id, EventType.ERROR, f"Task failed: {task_obj.title} — {e}")

    # README
    rprint("\n  📝 Generating README...")
    try:
        generator.generate_project_readme(parsed, tasks, project_name)
    except Exception as e:
        rprint(f"  [yellow]README skipped: {e}[/yellow]")

    project.status          = ProjectStatus.DONE
    project.tasks           = [t.to_dict() for t in tasks]
    project.generated_files = [f.path for f in all_files]
    project.project_dir     = str(fm.get_project_path(project_name))
    mem.save_project(project)

    done_count = sum(1 for t in tasks if t.status == TaskStatus.DONE)
    rprint(Panel(
        f"[bold green]✅ Done![/bold green]\n\n"
        f"Name:     {project_name}\n"
        f"Tasks:    {done_count}/{len(tasks)} completed\n"
        f"Files:    {len(all_files)} generated\n"
        f"Location: generated_projects/{project_name.lower().replace(' ', '_')}/",
        title="🎉 Project Generated",
        border_style="green",
    ))
    rprint("\n📂  Structure:")
    rprint(fm.print_tree(project_name))


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

@app.command()
def generate(
    project:    str           = typer.Option(..., "--project", "-p"),
    task_title: Optional[str] = typer.Option(None, "--task", "-t"),
):
    """⚙️  Generate code for pending tasks in an existing project."""
    fm, mem, _, _, generator, _, _ = _modules()
    proj = mem.load_project_by_name(project) or mem.load_project(project)
    if not proj:
        rprint(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    from app.models.schemas import IdeaParsed, Task
    parsed    = IdeaParsed.from_dict(proj.parsed_idea)
    all_tasks = [Task.from_dict(t) for t in proj.tasks]
    targets   = ([t for t in all_tasks if task_title.lower() in t.title.lower()]
                 if task_title else
                 [t for t in all_tasks if t.status == TaskStatus.PENDING])

    if not targets:
        rprint("[yellow]No matching / pending tasks found.[/yellow]")
        return

    for i, task_obj in enumerate(targets, 1):
        rprint(f"\n  [{i}/{len(targets)}] {task_obj.title}")
        with Progress(SpinnerColumn(), TextColumn("    [dim]{task.description}"), console=console) as p:
            gt = p.add_task("Generating...", total=None)
            try:
                gf = generator.generate_for_task(task_obj, parsed, proj.name)
                task_obj.status = TaskStatus.DONE
                p.update(gt, description=f"✅ {len(gf)} file(s)")
            except Exception as e:
                task_obj.status = TaskStatus.FAILED
                p.update(gt, description=f"❌ {e}")

    task_map = {t.id: t for t in all_tasks}
    for t in targets:
        task_map[t.id] = t
    proj.tasks = [t.to_dict() for t in task_map.values()]
    mem.save_project(proj)
    rprint("\n[green]✅ Generation complete.[/green]")


# ---------------------------------------------------------------------------
# debug
# ---------------------------------------------------------------------------

@app.command()
def debug(
    project:  str           = typer.Option(..., "--project", "-p"),
    file:     str           = typer.Option(..., "--file",    "-f"),
    error:    Optional[str] = typer.Option(None, "--error",  "-e"),
    no_apply: bool          = typer.Option(False, "--no-apply"),
):
    """🐛  Debug an error in a project file."""
    fm, mem, _, _, _, debugger, _ = _modules()
    proj = mem.load_project_by_name(project) or mem.load_project(project)
    if not proj:
        rprint(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    if not error:
        error = typer.prompt("Paste the error message / traceback")

    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}"), console=console) as p:
        t = p.add_task("Analysing error...", total=None)
        try:
            result = debugger.debug(file, error, proj.name, auto_apply=not no_apply)
            p.update(t, description="✅ Analysis complete")
        except FileNotFoundError as e:
            rprint(f"[red]{e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            rprint(f"[red]Debug failed:[/red] {e}")
            raise typer.Exit(1)

    rprint(debugger.display(result))
    if not no_apply:
        rprint(f"\n[green]✅ Patch applied to {file}[/green]")

    mem.log_event(proj.id, EventType.DEBUG_RUN, f"Debugged: {file}",
                  {"confidence": result.confidence})


# ---------------------------------------------------------------------------
# refactor
# ---------------------------------------------------------------------------

@app.command()
def refactor(
    project:  str           = typer.Option(..., "--project", "-p"),
    file:     Optional[str] = typer.Option(None, "--file", "-f"),
    focus:    Optional[str] = typer.Option(None, "--focus"),
    no_apply: bool          = typer.Option(False, "--no-apply"),
):
    """♻️  Refactor a file or entire project."""
    fm, mem, _, _, _, _, refactor_eng = _modules()
    proj = mem.load_project_by_name(project) or mem.load_project(project)
    if not proj:
        rprint(f"[red]Project not found:[/red] {project}")
        raise typer.Exit(1)

    focus_areas = [f.strip() for f in focus.split(",")] if focus else None

    if file:
        with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}"), console=console) as p:
            t = p.add_task("Refactoring...", total=None)
            try:
                result = refactor_eng.refactor_file(file, proj.name, focus_areas, auto_apply=not no_apply)
                p.update(t, description="✅ Done")
            except Exception as e:
                rprint(f"[red]Refactor failed:[/red] {e}")
                raise typer.Exit(1)
        rprint(refactor_eng.display(result))
        if no_apply:
            rprint(Syntax(result.refactored_code, _guess_lexer(file), theme="monokai", line_numbers=True))
    else:
        results = refactor_eng.refactor_project(proj.name, focus_areas=focus_areas)
        rprint(f"\n[green]✅ Refactored {len(results)} file(s)[/green]")
        for r in results:
            rprint(f"  • {r.file_path} — {len(r.changes_made)} change(s)")

    mem.log_event(proj.id, EventType.REFACTOR_RUN, f"Refactored: {file or 'all'}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@app.command(name="list")
def list_projects():
    """📋  List all saved projects."""
    _, mem, *_ = _modules()
    projects   = mem.list_projects()
    if not projects:
        rprint("[yellow]No projects yet. Run: python -m app.main new[/yellow]")
        return

    table = Table(title="💼  Projects", show_header=True, header_style="bold cyan")
    table.add_column("Name",    style="bold white")
    table.add_column("Status",  style="cyan")
    table.add_column("Tasks",   justify="right")
    table.add_column("Files",   justify="right")
    table.add_column("Updated", style="dim")

    icons = {"created":"🔵","planning":"🟡","generating":"🟠","done":"🟢","archived":"⚫"}
    for proj in projects:
        done = sum(1 for t in proj.tasks if t.get("status") == "done")
        table.add_row(
            proj.name,
            f"{icons.get(proj.status.value,'⚪')} {proj.status.value}",
            f"{done}/{len(proj.tasks)}",
            str(len(proj.generated_files)),
            proj.updated_at[:16].replace("T", " "),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status(project: str = typer.Argument(...)):
    """📊  Show detailed project status and file tree."""
    fm, mem, *_ = _modules()
    proj = mem.load_project_by_name(project) or mem.load_project(project)
    if not proj:
        rprint(f"[red]Not found:[/red] {project}")
        raise typer.Exit(1)

    rprint(Panel(
        f"[bold white]{proj.name}[/bold white]\n"
        f"Status:  {proj.status.value}\n"
        f"ID:      {proj.id}\n"
        f"Created: {proj.created_at[:16].replace('T',' ')}\n"
        f"Updated: {proj.updated_at[:16].replace('T',' ')}",
        title="📋 Project", border_style="cyan",
    ))

    if proj.tasks:
        from app.models.schemas import Task
        table = Table(title="Tasks", show_header=True, header_style="bold cyan")
        table.add_column("Title",    style="white")
        table.add_column("Priority", justify="center")
        table.add_column("Status",   justify="center")
        s_icons = {"pending":"⏳","in_progress":"🔄","done":"✅","failed":"❌"}
        p_colors = {"high":"red","medium":"yellow","low":"green"}
        for td in proj.tasks:
            t = Task.from_dict(td)
            table.add_row(
                t.title,
                f"[{p_colors.get(t.priority.value,'white')}]{t.priority.value}[/{p_colors.get(t.priority.value,'white')}]",
                f"{s_icons.get(t.status.value,'❓')} {t.status.value}",
            )
        console.print(table)

    if fm.project_exists(proj.name):
        rprint("\n📂  Files:")
        rprint(fm.print_tree(proj.name))


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

@app.command()
def history(
    project: str = typer.Argument(...),
    limit:   int = typer.Option(20, "--limit", "-l"),
):
    """📜  Show event history for a project."""
    _, mem, *_ = _modules()
    proj = mem.load_project_by_name(project) or mem.load_project(project)
    if not proj:
        rprint(f"[red]Not found:[/red] {project}")
        raise typer.Exit(1)

    events = mem.get_project_history(proj.id)[-limit:]
    if not events:
        rprint(f"[yellow]No events for: {project}[/yellow]")
        return

    table = Table(title=f"📜 History: {proj.name}", header_style="bold cyan")
    table.add_column("Time",    style="dim")
    table.add_column("Type",    style="cyan")
    table.add_column("Message", style="white")
    for ev in events:
        table.add_row(ev.timestamp[:19].replace("T"," "), ev.event_type.value, ev.message[:80])
    console.print(table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _idea_to_name(idea: str) -> str:
    import re
    words = idea.strip().split()[:4]
    slug  = "_".join(w.lower() for w in words)
    return re.sub(r"[^\w_]", "", slug) or "my_project"


def _guess_lexer(fp: str) -> str:
    from pathlib import Path
    return {".py":"python",".js":"javascript",".ts":"typescript",
            ".html":"html",".css":"css",".md":"markdown",".sh":"bash"
            }.get(Path(fp).suffix.lower(), "text")


if __name__ == "__main__":
    app()
