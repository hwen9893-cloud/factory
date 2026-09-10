"""CLI: collect args, call FactoryService, print results.

Usage after `pip install -e .`:

    factory init my_novel
    factory architect
    factory continue
    factory models
    factory stats
    factory demo
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from factory.demo import run_offline_demo
from factory.events import (
    ERROR,
    STAGE_COMPLETED,
    STAGE_STARTED,
    TOKEN,
    WARNING,
    WORKFLOW_COMPLETED,
    WORKFLOW_STARTED,
    WorkflowEvent,
    agent_for_stage,
)
from factory.models.usage import format_report
from factory.models.registry import format_registry
from factory.pipeline.models import PipelineError
from factory.service import FactoryService
from factory.settings import Settings, load_settings

DEFAULT_SEED = "灵根残缺少年在宗门试炼中被逼入绝境，借旧伤中残留的古剑灵息反击。"

app = typer.Typer(
    name="factory",
    help="AI novel factory",
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
memory_app = typer.Typer(help="Show layered story memory")
character_app = typer.Typer(help="List characters")
plot_app = typer.Typer(help="List plot threads")
app.add_typer(memory_app, name="memory")
app.add_typer(character_app, name="character")
app.add_typer(plot_app, name="plot")

BookOpt = Annotated[Optional[str], typer.Option("--book", "-b", help="Book id (default: last init / FACTORY_BOOK)")]

_cli_config: Path | None = None
_cli_overrides: dict[str, Any] = {}


def main(argv: Optional[list[str]] = None) -> int:
    """Entry used by tests. Console script calls `app` directly."""
    try:
        app(args=list(argv) if argv is not None else None)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return int(code) if isinstance(code, int) else 1
    return 0


@app.callback()
def _global_opts(
    config: Optional[Path] = typer.Option(None, "--config", help="Project YAML, merged over config/default.yaml"),
    provider: Optional[str] = typer.Option(None, "--provider", help="Override every model profile's provider"),
) -> None:
    global _cli_config, _cli_overrides
    _cli_config = config
    _cli_overrides = {}
    if provider:
        _cli_overrides["provider"] = provider


@app.command("init")
def init_cmd(
    name: str = typer.Argument(..., help="New book id"),
    title: str = typer.Option("", "--title"),
    genre: str = typer.Option("修仙爽文", "--genre"),
    style: str = typer.Option("克制、短句、先抑后扬", "--style"),
    seed: str = typer.Option(DEFAULT_SEED, "--seed"),
) -> None:
    """Create a book directory and select it."""
    service = _service()
    path = _try(
        lambda: service.init_book(name, title=title, genre=genre, style=style, seed=seed)
    )
    typer.echo(f"created  {name}")
    typer.echo(f"path     {path}")
    typer.echo("next     factory architect")


@app.command("status")
def status_cmd(book: BookOpt = None) -> None:
    """Show current book progress."""
    service, book_id = _boot(book)
    info = _try(lambda: service.book_status(book_id))
    typer.echo(book_id)
    typer.echo(f"  {info.title}  {info.genre}")
    if info.outlined:
        nxt = info.next_chapter if info.next_chapter is not None else "done"
        typer.echo(f"  chapter  {info.completed}/{info.outlined}   next {nxt}")
    else:
        last = info.last_final or "—"
        typer.echo(f"  chapter  {last}   next {info.next_chapter or 1}   (no outline)")
    typer.echo(f"  volume   {info.volume}")
    typer.echo(f"  outline  {'yes' if info.has_outline else 'no'}")
    typer.echo(f"  last     {f'ch{info.last_final:03d}' if info.last_final else '—'}")


@app.command("architect")
def architect_cmd(book: BookOpt = None) -> None:
    """World, characters, story spine, and book outline."""
    service, book_id = _boot(book)
    result = _try(lambda: service.architect(book_id))
    title = (result.get("outline") or result.get("architecture") or {}).get("title") or book_id
    typer.echo(f"architect  {book_id}  {title}")
    typer.echo("next        factory plan-volume 1   or   factory continue")


@app.command("plan-volume")
def plan_volume_cmd(
    volume: int = typer.Argument(..., help="Volume number"),
    book: BookOpt = None,
) -> None:
    """Plan one volume from the outline."""
    service, book_id = _boot(book)
    result = _try(lambda: service.plan_volume(book_id, volume))
    plan = result.get("volume_plan") or {}
    chapters = plan.get("chapters") or []
    typer.echo(f"volume {volume}  {plan.get('title') or ''}  {len(chapters)} chapters")


@app.command("plan-chapter")
def plan_chapter_cmd(
    chapter: int = typer.Argument(..., help="Chapter number"),
    book: BookOpt = None,
) -> None:
    """Build the chapter task (scene cards)."""
    service, book_id = _boot(book)
    result = _try(lambda: service.plan(book_id, chapter))
    plan = result.get("chapter_plan") or {}
    scenes = plan.get("scenes") or []
    typer.echo(f"ch {chapter}  {plan.get('title') or ''}  {len(scenes)} scenes")


@app.command("write")
def write_cmd(
    chapter: int = typer.Argument(..., help="Chapter number"),
    book: BookOpt = None,
) -> None:
    """Write chapter prose from the chapter plan."""
    service, book_id = _boot(book)
    result = _try(lambda: service.generate(book_id, chapter))
    typer.echo(_chapter_line(result, prefix="wrote"))


@app.command("review")
def review_cmd(
    chapter: int = typer.Argument(..., help="Chapter number"),
    book: BookOpt = None,
) -> None:
    """Continuity check + quality review. Does not rewrite."""
    service, book_id = _boot(book)
    result = _try(lambda: service.review(book_id, chapter))
    continuity = result.get("continuity") or {}
    review = result.get("review") or {}
    typer.echo(_chapter_line(result, prefix="review"))
    typer.echo(
        f"  continuity  {'pass' if continuity.get('passed', True) else continuity.get('severity', 'fail')}"
        f"   score {review.get('score', '-')}"
        f"   {'pass' if review.get('pass', review.get('passed', True)) else 'fail'}"
    )
    must = review.get("must_fix") or []
    if must:
        typer.echo(f"  must_fix    {'; '.join(str(item) for item in must[:3])}")


@app.command("revise")
def revise_cmd(
    chapter: int = typer.Argument(..., help="Chapter number"),
    book: BookOpt = None,
) -> None:
    """Rewrite the draft from the latest review / continuity notes."""
    service, book_id = _boot(book)
    result = _try(lambda: service.revise(book_id, chapter))
    typer.echo(_chapter_line(result, prefix="revised"))


@app.command("continue")
def continue_cmd(book: BookOpt = None) -> None:
    """Detect the next chapter and run plan → write → check → revise → save → memory."""
    service, book_id = _boot(book)
    status = _try(lambda: service.book_status(book_id))
    if not status.has_outline:
        _fail("no outline. run: factory architect")
    if status.next_chapter is None:
        typer.echo(f"{book_id}  done  {status.completed}/{status.outlined} chapters")
        raise typer.Exit(0)
    typer.echo(f"{book_id}  chapter {status.next_chapter}{'  resume' if status.next_resumable else ''}")
    result = _try(
        lambda: service.produce_chapter(
            book_id,
            status.next_chapter,
            resume=status.next_resumable,
        )
    )
    typer.echo(_chapter_line(result, prefix="done"))
    pipe = result.get("pipeline") or {}
    if pipe.get("status"):
        typer.echo(f"  pipeline  {pipe.get('status')}  revisions {pipe.get('revision_attempts', 0)}")


@memory_app.command("show")
def memory_show(book: BookOpt = None) -> None:
    """Print canon facts, open threads, and recent chapter summaries."""
    service, book_id = _boot(book)
    memory = _try(lambda: service.memory_overview(book_id))
    typer.echo(book_id)
    typer.echo(f"  conflict  {memory.get('conflict') or '—'}")
    typer.echo(f"  facts     {len(memory.get('facts') or [])}")
    threads = memory.get("threads") or []
    if threads:
        typer.echo("  threads")
        for thread in threads[:12]:
            typer.echo(f"    open   {thread.get('id') or '—'}  {thread.get('text') or ''}")
    else:
        typer.echo("  threads   —")
    recent = memory.get("recent") or []
    if recent:
        typer.echo("  recent")
        for item in recent:
            typer.echo(f"    ch{int(item.get('ch_no') or 0):03d}  {item.get('summary') or '—'}")


@character_app.command("list")
def character_list(book: BookOpt = None) -> None:
    """List character cards."""
    service, book_id = _boot(book)
    rows = _try(lambda: service.list_characters(book_id))
    if not rows:
        typer.echo(f"{book_id}  (no characters)")
        return
    typer.echo(book_id)
    for item in rows:
        realm = item.get("cultivation_realm") or item.get("realm") or ""
        typer.echo(
            f"  {item.get('id') or '—'}  {item.get('name') or '—'}"
            f"  {realm}  {item.get('status') or 'alive'}"
        )


@plot_app.command("list")
def plot_list(book: BookOpt = None) -> None:
    """List plot threads and foreshadowing."""
    service, book_id = _boot(book)
    payload = _try(lambda: service.list_plot(book_id))
    typer.echo(book_id)
    threads = payload.get("threads") or []
    clues = payload.get("foreshadowing") or []
    if not threads and not clues:
        typer.echo("  (no plot threads)")
        return
    for thread in threads:
        typer.echo(f"  {str(thread.get('status') or ''):10}  {thread.get('id') or '—'}  {thread.get('title') or ''}")
    for clue in clues:
        mark = "resolved" if clue.get("resolved") else "open"
        typer.echo(f"  {mark:10}  {clue.get('id') or '—'}  {clue.get('clue') or ''}")


@app.command("stats")
def stats_cmd(
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Only this book (default: all books)"),
) -> None:
    """Show today's model calls, tokens, cost, and per-agent / per-model usage."""
    service = _service()
    typer.echo(format_report(_try(lambda: service.usage_summary(book_id=book))))


@app.command("models")
def models_cmd() -> None:
    """List providers, named models, and agent assignments from config."""
    service = _service()
    typer.echo(_try(lambda: format_registry(service.registry)))


@app.command("studio")
def studio_cmd(
    book: BookOpt = None,
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
) -> None:
    """Open Novel Factory GUI. Needs the gui extra: pip install -e '.[gui]'."""
    _quiet_logs()
    try:
        import nicegui  # noqa: F401
    except ImportError:
        _fail('Chapter Studio needs NiceGUI. pip install -e ".[gui]"')
    from factory.gui.app import run_studio

    run_studio(book=book, host=host, port=port, settings=_load_settings())


@app.command("demo")
def demo_cmd(
    out: Optional[Path] = typer.Option(None, "--out", help="Write the demo book here (default: a temp directory)"),
) -> None:
    """Run an offline mock pipeline: init → architect → one chapter. No live API."""
    import tempfile

    _quiet_logs()
    tmp: tempfile.TemporaryDirectory[str] | None = None
    if out is None:
        tmp = tempfile.TemporaryDirectory(prefix="factory-demo-")
        out = Path(tmp.name)
    try:
        report = run_offline_demo(out)
    except Exception as exc:
        if tmp is not None:
            tmp.cleanup()
        _fail(str(exc))
        return
    typer.echo("offline demo  (provider=mock, no live API)")
    typer.echo(f"  book     {report.book_dir}")
    typer.echo(f"  title    {report.title}")
    typer.echo(f"  chapter  {report.chapter_path}")
    typer.echo(f"  pipeline {report.pipeline_status}")
    if report.body_preview:
        typer.echo("  preview")
        for line in report.body_preview.splitlines()[:6]:
            typer.echo(f"    {line}")
    if report.missing:
        typer.echo("  missing  " + ", ".join(report.missing), err=True)
    if not report.ok:
        if tmp is not None:
            tmp.cleanup()
        _fail("demo failed")
        return
    typer.echo("demo passed")
    if tmp is not None:
        typer.echo("  (temp dir removed; pass --out DIR to keep files)")
        tmp.cleanup()


def _quiet_logs() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")


def _load_settings() -> Settings:
    return load_settings(_cli_config, overrides=_cli_overrides or None)


def _service() -> FactoryService:
    _quiet_logs()
    return FactoryService(_load_settings(), on_progress=print_progress)


def print_progress(event: WorkflowEvent) -> None:
    """CLI renderer. Token deltas stay off stdout."""
    if event.type in {TOKEN, WORKFLOW_STARTED, WORKFLOW_COMPLETED}:
        return
    if event.type == STAGE_STARTED:
        print(f"→ {_cli_stage_text(event.stage)}", flush=True)
    elif event.type == STAGE_COMPLETED:
        print("  ok", flush=True)
    elif event.type == ERROR:
        print(f"  error: {event.message}", flush=True)
    elif event.type == WARNING and event.message:
        print(event.message, flush=True)
    elif event.message:
        print(event.message, flush=True)


_CLI_STAGE_TEXT = {
    "chapter_planner": "Planning",
    "chapter_writer": "Writing",
    "continuity_check": "Checking continuity",
    "continuity": "Checking continuity",
    "quality_review": "Reviewing",
    "reviewer": "Reviewing",
    "revision": "Revising",
    "memory_update": "Updating memory",
    "memory": "Updating memory",
    "volume_planner": "Planning volume",
    "save": "Saving",
    "persist": "Saving",
}


def _cli_stage_text(stage: str) -> str:
    return _CLI_STAGE_TEXT.get(stage) or _CLI_STAGE_TEXT.get(agent_for_stage(stage)) or stage


def _boot(book: str | None) -> tuple[FactoryService, str]:
    service = _service()
    return service, _try(lambda: service.require_book(book))


def _try(fn):
    try:
        return fn()
    except PipelineError as exc:
        _fail(f"failed at {exc.stage}: {exc}")
        raise AssertionError
    except (LookupError, ValueError, FileExistsError, FileNotFoundError, KeyError) as exc:
        _fail(str(exc))
        raise AssertionError


def _chapter_line(result: dict[str, Any], *, prefix: str) -> str:
    ch_no = result.get("ch_no") or ""
    title = result.get("title") or ""
    words = result.get("word_count")
    extra = f"  {words}字" if words else ""
    return f"{prefix}  ch {ch_no}  {title}{extra}".rstrip()


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
