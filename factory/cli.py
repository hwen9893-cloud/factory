"""CLI: factory init / status / architect / plan-* / write / review / revise / continue.

Usage after `pip install -e .`:

    factory init my_novel
    factory architect
    factory continue
    factory stats
    factory demo
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated, Any, Iterable, Optional

import typer

from factory.demo import run_offline_demo
from factory.models.usage import UsageStore, format_report
from factory.pipeline.models import PipelineError
from factory.schema.store import SchemaStore
from factory.settings import Settings, load_settings
from factory.storage import BookRepository
from factory.workflow import SimpleWorkflow

DEFAULT_SEED = "灵根残缺少年在宗门试炼中被逼入绝境，借旧伤中残留的古剑灵息反击。"

ARCHITECT_STEPS = ("world_builder", "character", "novel_architect", "outline")
CHAPTER_STEPS = ("chapter_planner", "chapter_writer", "continuity", "reviewer", "revision", "memory")

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
    _quiet_logs()
    settings = _load_settings()
    repo = BookRepository(settings.data_dir)
    try:
        repo.init_book(name, title=title or name, genre=genre, style=style, story_seed=seed)
    except FileExistsError as exc:
        _fail(str(exc))
    repo.set_current_book(name)
    typer.echo(f"created  {name}")
    typer.echo(f"path     {repo.book_dir(name)}")
    typer.echo("next     factory architect")


@app.command("status")
def status_cmd(book: BookOpt = None) -> None:
    """Show current book progress."""
    settings, repo, book_id = _boot(book)
    wf = SimpleWorkflow(settings, book_id)
    ctx = wf.context
    outlined = ctx.outlined_chapters()
    done = sum(1 for ch_no in outlined if repo.load_final(book_id, ch_no))
    nxt = _next_chapter(repo, ctx)
    last = repo.max_final_chapter(book_id)
    typer.echo(book_id)
    typer.echo(f"  {ctx.title}  {ctx.genre}")
    if outlined:
        typer.echo(f"  chapter  {done}/{len(outlined)}   next {nxt if nxt is not None else 'done'}")
    else:
        typer.echo(f"  chapter  {last or '—'}   next {nxt or 1}   (no outline)")
    typer.echo(f"  volume   {ctx.current_volume}")
    typer.echo(f"  outline  {'yes' if ctx.outline else 'no'}")
    typer.echo(f"  last     {f'ch{last:03d}' if last else '—'}")


@app.command("architect")
def architect_cmd(book: BookOpt = None) -> None:
    """World, characters, story spine, and book outline."""
    settings, repo, book_id = _boot(book)
    result = _run(settings, book_id, ARCHITECT_STEPS)
    title = (result.get("outline") or result.get("architecture") or {}).get("title") or book_id
    typer.echo(f"architect  {book_id}  {title}")
    typer.echo("next        factory plan-volume 1   or   factory continue")


@app.command("plan-volume")
def plan_volume_cmd(
    volume: int = typer.Argument(..., help="Volume number"),
    book: BookOpt = None,
) -> None:
    """Plan one volume from the outline."""
    settings, repo, book_id = _boot(book)
    result = _run(settings, book_id, ("volume_planner",), volume_no=volume)
    plan = result.get("volume_plan") or {}
    chapters = plan.get("chapters") or []
    typer.echo(f"volume {volume}  {plan.get('title') or ''}  {len(chapters)} chapters")


@app.command("plan-chapter")
def plan_chapter_cmd(
    chapter: int = typer.Argument(..., help="Chapter number"),
    book: BookOpt = None,
) -> None:
    """Build the chapter task (scene cards)."""
    settings, repo, book_id = _boot(book)
    _ensure_volume(settings, book_id, chapter)
    result = _run(settings, book_id, ("chapter_planner",), ch_no=chapter)
    plan = result.get("chapter_plan") or {}
    scenes = plan.get("scenes") or []
    typer.echo(f"ch {chapter}  {plan.get('title') or ''}  {len(scenes)} scenes")


@app.command("write")
def write_cmd(
    chapter: int = typer.Argument(..., help="Chapter number"),
    book: BookOpt = None,
) -> None:
    """Write chapter prose from the chapter plan."""
    settings, repo, book_id = _boot(book)
    result = _run(settings, book_id, ("chapter_writer",), ch_no=chapter)
    typer.echo(_chapter_line(result, prefix="wrote"))


@app.command("review")
def review_cmd(
    chapter: int = typer.Argument(..., help="Chapter number"),
    book: BookOpt = None,
) -> None:
    """Continuity check + quality review. Does not rewrite."""
    settings, repo, book_id = _boot(book)
    result = _run(settings, book_id, ("continuity", "reviewer"), ch_no=chapter)
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
    settings, repo, book_id = _boot(book)
    result = _run(settings, book_id, ("revision",), ch_no=chapter)
    typer.echo(_chapter_line(result, prefix="revised"))


@app.command("continue")
def continue_cmd(book: BookOpt = None) -> None:
    """Detect the next chapter and run plan → write → check → revise → save → memory."""
    settings, repo, book_id = _boot(book)
    wf = SimpleWorkflow(settings, book_id)
    if not wf.context.outline:
        _fail("no outline. run: factory architect")
    ch_no = _next_chapter(repo, wf.context)
    if ch_no is None:
        outlined = wf.context.outlined_chapters()
        typer.echo(f"{book_id}  done  {len(outlined)}/{len(outlined)} chapters")
        raise typer.Exit(0)
    volume_no = wf.context.volume_for_chapter(ch_no)
    if not repo.load_volume_plan(book_id, volume_no):
        typer.echo(f"{book_id}  planning volume {volume_no}")
        wf.context.current_volume = volume_no
        wf.context.current_chapter = ch_no
        wf.context.save_meta(wf.repo)
        _invoke(wf, ("volume_planner",), volume_no=volume_no, ch_no=ch_no)
    pipe = repo.load_pipeline_state(book_id, ch_no) or {}
    wf.resume = pipe.get("status") in {"failed", "running"}
    wf.context.current_chapter = ch_no
    wf.context.current_volume = volume_no
    wf.context.volume_plan = repo.load_volume_plan(book_id, volume_no)
    wf.context.save_meta(wf.repo)
    typer.echo(f"{book_id}  chapter {ch_no}{'  resume' if wf.resume else ''}")
    result = _invoke(wf, CHAPTER_STEPS, ch_no=ch_no, volume_no=volume_no)
    typer.echo(_chapter_line(result, prefix="done"))
    status = (result.get("pipeline") or {}).get("status")
    if status:
        typer.echo(f"  pipeline  {status}  revisions {(result.get('pipeline') or {}).get('revision_attempts', 0)}")


@memory_app.command("show")
def memory_show(book: BookOpt = None) -> None:
    """Print canon facts, open threads, and recent chapter summaries."""
    settings, repo, book_id = _boot(book)
    wf = SimpleWorkflow(settings, book_id)
    memory = wf.memory_store.load()
    chapters = wf.memory_store.load_chapter_memories(last_n=5)
    typer.echo(book_id)
    typer.echo(f"  conflict  {memory.plot.current_conflict or '—'}")
    typer.echo(f"  facts     {len(memory.canon.facts)}")
    if memory.plot.open_threads:
        typer.echo("  threads")
        for thread in memory.plot.open_threads[:12]:
            typer.echo(f"    open   {thread.id}  {thread.text}")
    else:
        typer.echo("  threads   —")
    if chapters:
        typer.echo("  recent")
        for item in chapters:
            typer.echo(f"    ch{item.ch_no:03d}  {item.summary or '—'}")


@character_app.command("list")
def character_list(book: BookOpt = None) -> None:
    """List character cards."""
    settings, repo, book_id = _boot(book)
    rows = repo.load_characters(book_id)
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
    settings, repo, book_id = _boot(book)
    schema = SchemaStore(repo, book_id).load()
    typer.echo(book_id)
    if not schema.plot_threads and not schema.foreshadowing:
        typer.echo("  (no plot threads)")
        return
    for thread in schema.plot_threads:
        typer.echo(f"  {thread.status:10}  {thread.id or '—'}  {thread.title}")
    for clue in schema.foreshadowing:
        mark = "resolved" if clue.resolved else "open"
        typer.echo(f"  {mark:10}  {clue.id or '—'}  {clue.clue}")


@app.command("stats")
def stats_cmd(
    book: Optional[str] = typer.Option(None, "--book", "-b", help="Only this book (default: all books)"),
) -> None:
    """Show today's model calls, tokens, cost, and per-agent / per-model usage."""
    _quiet_logs()
    settings = _load_settings()
    store = UsageStore(settings.data_dir / "usage.sqlite")
    typer.echo(format_report(store.summarize(since=store.today_start(), book_id=book)))


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


def _boot(book: str | None) -> tuple[Settings, BookRepository, str]:
    _quiet_logs()
    settings = _load_settings()
    repo = BookRepository(settings.data_dir)
    book_id = _resolve_book(book, settings, repo)
    if not repo.exists(book_id):
        _fail(f"book not found: {book_id}. factory init {book_id}")
    repo.set_current_book(book_id)
    return settings, repo, book_id


def _resolve_book(explicit: str | None, settings: Settings, repo: BookRepository) -> str:
    for candidate in (explicit, os.environ.get("FACTORY_BOOK"), repo.current_book(), settings.default_book):
        if candidate:
            return candidate
    _fail("no book selected. factory init <name>")
    raise AssertionError


def _run(
    settings: Settings,
    book_id: str,
    steps: Iterable[str],
    *,
    ch_no: int | None = None,
    volume_no: int | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    wf = SimpleWorkflow(settings, book_id)
    wf.resume = resume
    return _invoke(wf, steps, ch_no=ch_no, volume_no=volume_no)


def _invoke(
    wf: SimpleWorkflow,
    steps: Iterable[str],
    *,
    ch_no: int | None = None,
    volume_no: int | None = None,
) -> dict[str, Any]:
    if ch_no:
        wf.context.current_chapter = ch_no
    if volume_no:
        wf.context.current_volume = volume_no
        loaded = wf.repo.load_volume_plan(wf.book_id, volume_no)
        if loaded:
            wf.context.volume_plan = loaded
    wf.context.save_meta(wf.repo)
    payload = {
        "story_seed": wf.context.story_seed,
        "ch_no": ch_no or wf.context.current_chapter,
        "volume_no": volume_no or wf.context.current_volume,
    }
    try:
        return wf.run(steps, payload)
    except PipelineError as exc:
        _fail(f"failed at {exc.stage}: {exc}")
        raise AssertionError
    except (KeyError, ValueError) as exc:
        _fail(str(exc))
        raise AssertionError


def _ensure_volume(settings: Settings, book_id: str, ch_no: int) -> None:
    wf = SimpleWorkflow(settings, book_id)
    if not wf.context.outline:
        _fail("no outline. run: factory architect")
    volume_no = wf.context.volume_for_chapter(ch_no)
    if wf.repo.load_volume_plan(book_id, volume_no):
        return
    typer.echo(f"planning volume {volume_no}")
    _invoke(wf, ("volume_planner",), volume_no=volume_no, ch_no=ch_no)


def _next_chapter(repo: BookRepository, ctx: Any) -> int | None:
    outlined = ctx.outlined_chapters()
    for ch_no in outlined:
        if not repo.load_final(ctx.book_id, ch_no):
            return ch_no
    if outlined:
        return None
    return (repo.max_final_chapter(ctx.book_id) or 0) + 1


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
