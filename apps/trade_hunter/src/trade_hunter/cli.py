import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from trade_hunter.config import RunConfig, _DEFAULT_DOWNLOADS_DIR, _DEFAULT_WORKSHEETS_DIR

app = typer.Typer()
console = Console()


@app.callback()
def _callback() -> None:
    """trade_hunter — option-selling candidate generator."""


@app.command()
def run(
    output_dir: Path = typer.Option(..., help="Directory where trade_signals.xlsx will be written"),
    downloads_dir: Path = typer.Option(
        _DEFAULT_DOWNLOADS_DIR,
        help="Directory to search for downloaded input files when explicit paths are omitted",
    ),
    worksheets_dir: Path = typer.Option(
        _DEFAULT_WORKSHEETS_DIR,
        help="Directory containing journal.xlsx",
    ),
    tastytrade_file: Path | None = typer.Option(
        None,
        help="TastyTrade CSV. If omitted, auto-discovered from --downloads-dir",
    ),
    bull_file: Path | None = typer.Option(
        None,
        help="SeekingAlpha BULL-ish Excel. If omitted, auto-discovered from --downloads-dir",
    ),
    bear_file: Path | None = typer.Option(
        None,
        help="SeekingAlpha BEAR-ish Excel. If omitted, auto-discovered from --downloads-dir",
    ),
    journal_file: Path | None = typer.Option(
        None,
        help="Active trades journal. If omitted, resolved as --worksheets-dir/journal.xlsx",
    ),
    min_open_interest: int = typer.Option(8, help="Minimum open interest hard filter"),
    min_bid: float = typer.Option(0.55, help="Minimum option bid hard filter"),
    max_spread_pct: float = typer.Option(
        0.13, help="Maximum spread % hard filter ((ask-bid)/mid, default 13%)"
    ),
    min_dte: int = typer.Option(30, help="Minimum days-to-expiration for expiration selection"),
    max_dte: int = typer.Option(60, help="Maximum days-to-expiration for expiration selection"),
    sandbox: bool = typer.Option(False, "--sandbox", help="Use Tradier sandbox environment"),
) -> None:
    """Generate ranked BULL-ish and BEAR-ish option-selling candidates."""
    load_dotenv()

    # --sandbox overrides TRADIER_ENV
    if not sandbox:
        tradier_env = os.environ.get("TRADIER_ENV", "production").strip().lower()
        sandbox = tradier_env == "sandbox"

    if sandbox:
        api_key = os.environ.get("TRADIER_SANDBOX_API_KEY", "")
        if not api_key:
            console.print(
                "[red]Error:[/red] TRADIER_SANDBOX_API_KEY is not set (required for sandbox mode).",
                err=True,
            )
            raise typer.Exit(code=1)
    else:
        api_key = os.environ.get("TRADIER_API_KEY", "")
        if not api_key:
            console.print("[red]Error:[/red] TRADIER_API_KEY is not set.", err=True)
            raise typer.Exit(code=1)

    config = RunConfig(
        output_dir=output_dir,
        tradier_api_key=api_key,
        downloads_dir=downloads_dir,
        worksheets_dir=worksheets_dir,
        tastytrade_file=tastytrade_file,
        bull_file=bull_file,
        bear_file=bear_file,
        journal_file=journal_file,
        min_open_interest=min_open_interest,
        min_bid=min_bid,
        max_spread_pct=max_spread_pct,
        min_dte=min_dte,
        max_dte=max_dte,
        sandbox=sandbox,
    )

    _print_summary(config)
    console.print("[yellow]Configuration loaded. Pipeline not yet implemented.[/yellow]")


def _auto_or_explicit(path: Path | None, downloads_dir: Path) -> str:
    return str(path) if path else f"auto-discover from {downloads_dir}"


def _print_summary(config: RunConfig) -> None:
    console.rule("trade_hunter run")
    console.print(
        f"  TastyTrade file   : {_auto_or_explicit(config.tastytrade_file, config.downloads_dir)}"
    )
    console.print(
        f"  BULL-ish file     : {_auto_or_explicit(config.bull_file, config.downloads_dir)}"
    )
    console.print(
        f"  BEAR-ish file     : {_auto_or_explicit(config.bear_file, config.downloads_dir)}"
    )
    journal_display = (
        str(config.journal_file) if config.journal_file else f"{config.worksheets_dir}/journal.xlsx"
    )
    console.print(f"  Journal file      : {journal_display}")
    console.print(f"  Output directory  : {config.output_dir}")
    env_label = "sandbox" if config.sandbox else "production"
    console.print(f"  Tradier API key   : ****  (set, {env_label})")
    console.rule()
    console.print(f"  Min open interest : {config.min_open_interest}")
    console.print(f"  Min bid           : {config.min_bid}")
    console.print(f"  Max spread %      : {config.max_spread_pct * 100:.1f}%")
    console.print(f"  DTE window        : {config.min_dte} \u2013 {config.max_dte}")
    console.rule()
