import sys

import click

from icloudphotonator import __version__


@click.group(context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="icloudphotonator")
@click.pass_context
def main(ctx: click.Context) -> None:
    """iCloudPhotonator — Intelligente Foto-Migration für Apple Fotos."""
    if ctx.invoked_subcommand is None and len(sys.argv) == 1:
        from icloudphotonator.ui.app import main as gui_main

        gui_main()


@main.command()
def gui() -> None:
    """Launch the graphical user interface."""
    from icloudphotonator.ui.app import main as gui_main

    gui_main()


@main.command(name="import-photos")
@click.argument("source", type=click.Path(exists=True))
@click.option(
    "--staging-dir",
    type=click.Path(),
    default=None,
    help="Local staging directory for network files",
)
@click.option(
    "--db-path",
    type=click.Path(),
    default=None,
    help="Database path for job persistence",
)
def import_photos(source: str, staging_dir: str | None, db_path: str | None) -> None:
    """Import photos from SOURCE folder (CLI mode)."""
    import asyncio
    from pathlib import Path

    from icloudphotonator.logging_config import setup_logging
    from icloudphotonator.orchestrator import ImportOrchestrator

    setup_logging()
    source_path = Path(source)
    staging = Path(staging_dir).expanduser() if staging_dir else Path.home() / ".icloudphotonator" / "staging"
    db = Path(db_path).expanduser() if db_path else Path.home() / ".icloudphotonator" / "icloudphotonator.db"

    click.echo(f"🖼️ iCloudPhotonator — Importing from: {source_path}")
    click.echo(f"📁 Staging: {staging}")
    click.echo(f"💾 Database: {db}")

    orchestrator = ImportOrchestrator(db_path=db, staging_dir=staging)

    def on_progress(stats: dict) -> None:
        imported = stats.get("imported", 0)
        total = stats.get("total", 0)
        errors = stats.get("errors", 0)
        click.echo(f"\r⏳ {imported}/{total} imported, {errors} errors", nl=False)

    orchestrator.on_progress(on_progress)

    try:
        asyncio.run(orchestrator.start_import(source_path))
        click.echo("\n✅ Import complete!")
    except KeyboardInterrupt:
        click.echo("\n⏸️ Import paused. Run again to resume.")
    except Exception as exc:
        click.echo(f"\n❌ Import failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()