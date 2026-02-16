from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import click

from judgefinder.bootstrap import AppContainer, create_app

LOGGER = logging.getLogger(__name__)


@click.group()
@click.option(
    "--config-path",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    default=Path("config/config.toml"),
    show_default=True,
)
@click.option("--verbose", is_flag=True, default=False, help="Enable debug logging.")
@click.pass_context
def app(ctx: click.Context, config_path: Path, verbose: bool) -> None:
    _configure_logging(verbose=verbose)
    container = create_app(config_path)
    ctx.obj = container


@app.command("collect")
@click.option("--date", "raw_date", default="today", show_default=True)
@click.pass_obj
def collect(container: AppContainer, raw_date: str) -> None:
    target_date = _resolve_date(raw_date=raw_date, timezone_name=container.config.timezone)
    LOGGER.debug("Collecting notices for %s", target_date.isoformat())
    notices = container.collect_use_case.execute(target_date)
    for notice in notices:
        click.echo(notice.url)


@app.command("list")
@click.option("--date", "raw_date", default="today", show_default=True)
@click.pass_obj
def list_notices(container: AppContainer, raw_date: str) -> None:
    target_date = _resolve_date(raw_date=raw_date, timezone_name=container.config.timezone)
    notices = container.list_use_case.execute(target_date)
    for notice in notices:
        click.echo(notice.url)


@app.command("sources")
@click.pass_obj
def list_sources(container: AppContainer) -> None:
    for slug in container.source_registry.list_enabled_source_slugs():
        click.echo(slug)


def _resolve_date(raw_date: str, timezone_name: str) -> date:
    if raw_date == "today":
        return datetime.now(tz=ZoneInfo(timezone_name)).date()
    try:
        return date.fromisoformat(raw_date)
    except ValueError as exc:
        raise click.BadParameter("Date must be 'today' or YYYY-MM-DD.") from exc


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


if __name__ == "__main__":
    app()
