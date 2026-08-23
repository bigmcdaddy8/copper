"""Dick's Laboratory command-line entry point."""
from __future__ import annotations

import typer

app = typer.Typer()


@app.callback()
def main() -> None:
    """dicks_laboratory - provider-neutral market-data research tools."""