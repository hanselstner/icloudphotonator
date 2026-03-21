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
def import_photos(source: str) -> None:
    """Import photos from SOURCE folder (CLI mode)."""
    click.echo(f"Importing from: {source}")


if __name__ == "__main__":
    main()