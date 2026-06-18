"""j2py CLI — Java to Python converter."""

from __future__ import annotations

import typer

from j2py.cli.analyze import analyze
from j2py.cli.compare import compare
from j2py.cli.doctor import dashboard, doctor, sarif
from j2py.cli.translate import translate
from j2py.cli.watch import watch

app = typer.Typer(
    name="j2py",
    help="Convert Java source files to Python.",
    add_completion=False,
)

app.command()(translate)
app.command()(dashboard)
app.command(context_settings={"allow_extra_args": True})(doctor)
app.command()(sarif)
app.command()(watch)
app.command()(analyze)
app.command()(compare)


if __name__ == "__main__":
    app()
