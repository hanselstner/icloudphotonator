import sys

# Argv-marker dispatch for the frozen PyInstaller bundle: when re-invoking
# ourselves as an osxphotos subprocess we cannot rely on `python -m osxphotos`
# because sys.executable is the bundle bootloader (which does not honour -m).
# This branch must run BEFORE any click decorators or icloudphotonator.* imports
# so that click never sees the `--run-osxphotos` argv and the GUI/app chain is
# not loaded inside the subprocess.
if len(sys.argv) >= 2 and sys.argv[1] == "--run-osxphotos":
    sys.argv = ["osxphotos"] + sys.argv[2:]
    from osxphotos.cli import cli_main

    sys.exit(cli_main() or 0)

import click

from icloudphotonator import __version__


@click.group(context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="icloudphotonator")
@click.pass_context
def main(ctx: click.Context) -> None:
    """iCloudPhotonator — Intelligent photo migration for Apple Photos."""
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
@click.option(
    "--album",
    type=str,
    default=None,
    help="Name of the import album (default: source folder name)",
)
@click.option(
    "--library",
    "--mediathek",
    type=click.Path(exists=True),
    default=None,
    help="Path to the target Photos library (.photoslibrary)",
)
def import_photos(
    source: str,
    staging_dir: str | None,
    db_path: str | None,
    album: str | None,
    library: str | None,
) -> None:
    """Import photos from SOURCE folder (CLI mode)."""
    import asyncio
    from pathlib import Path

    from icloudphotonator.logging_config import setup_logging
    from icloudphotonator.orchestrator import ImportOrchestrator

    setup_logging()
    source_path = Path(source)
    staging = Path(staging_dir).expanduser() if staging_dir else Path.home() / ".icloudphotonator" / "staging"
    db = Path(db_path).expanduser() if db_path else Path.home() / ".icloudphotonator" / "icloudphotonator.db"
    target_album = source_path.name if album is None else album
    target_library = Path(library).expanduser() if library else None

    click.echo(f"🖼️ iCloudPhotonator — Importing from: {source_path}")
    click.echo(f"📁 Staging: {staging}")
    click.echo(f"💾 Database: {db}")
    if target_album:
        click.echo(f"🗂️ Album: {target_album}")
    if target_library is not None:
        click.echo(f"📚 Library: {target_library}")

    orchestrator = ImportOrchestrator(db_path=db, staging_dir=staging, library=target_library, album=target_album)

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


@main.command(name="retry-errors")
@click.option("--db-path", type=click.Path(), default=None)
def retry_errors(db_path: str | None) -> None:
    """Reset errored files to pending for retry."""
    from pathlib import Path

    from icloudphotonator.db import Database

    db_file = Path(db_path).expanduser() if db_path else Path.home() / ".icloudphotonator" / "icloudphotonator.db"
    db = Database(db_file)
    latest_job = db.get_latest_job()
    if latest_job is None:
        click.echo("No jobs found.")
        return

    reset_count = db.reset_error_files(latest_job["id"])
    click.echo(f"🔄 {reset_count} error files reset for job {latest_job['id']}.")


def _early_fda_registration_probe() -> None:
    """Force a real open(2) on a TCC-protected path before any subprocess
    or AppleEvent might re-attribute our process. This guarantees the TCC
    record is staged against com.hanselstner.icloudphotonator (our bundle
    identity), not against any parent terminal that launched us during dev."""
    import os

    candidates = [
        os.path.expanduser("~/Library/Safari/Bookmarks.plist"),
        os.path.expanduser("~/Library/Mail"),
        os.path.expanduser("~/Library/Messages"),
    ]
    for path in candidates:
        try:
            fd = os.open(path, os.O_RDONLY)
        except (PermissionError, FileNotFoundError, OSError):
            continue
        else:
            try:
                os.read(fd, 1)
            finally:
                os.close(fd)
            return


if __name__ == "__main__":
    # Skip probe in osxphotos subprocess (argv-marker already rewrote sys.argv
    # to start with "osxphotos" and called sys.exit; this is belt-and-suspenders
    # in case the argv-marker logic ever changes).
    if not (len(sys.argv) >= 1 and sys.argv[0] == "osxphotos"):
        _early_fda_registration_probe()
    main()