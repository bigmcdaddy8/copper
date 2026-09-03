"""Pre-arm credential + instrument preflight for long-horizon ES capture.

0W-2D: proves OAuth/REST reachability, the futures endpoint, and that /ESU6
resolves to /ESU26:XCME -- WITHOUT requesting a DXLink quote token. Requesting
the quote token early starts its ~24h lifetime and was the 0W-2 Attempt-3
KNOWN_GAP root cause (see docs/dicks_laboratory 0W-2C / 0W-2D). Prints only
booleans / counts. Exit 0 = PASS.

Run this at arming time; run `dicks_lab_collect_es.py` (which obtains the quote
token at startup) at the actual session launch.
"""
from __future__ import annotations

import typer
from dotenv import load_dotenv

from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.settings import TastytradeSettings
from dicks_laboratory.preflight import run_credential_preflight

app = typer.Typer(add_completion=False)
_SYMBOL = "/ESU6"
_EXPECTED_STREAMER = "/ESU26:XCME"


@app.command()
def preflight() -> None:
    """Run the pre-arm safe credential/instrument checks (no quote token)."""
    load_dotenv()
    client = TastytradeClient(TastytradeSettings.from_environment("tastytrade_production"))
    result = run_credential_preflight(client, _SYMBOL, _EXPECTED_STREAMER)
    typer.echo(f"rest_reachable={str(result.rest_reachable).lower()}")
    typer.echo(
        f"futures_endpoint_usable={str(result.futures_endpoint_usable).lower()} "
        f"count={result.futures_count}"
    )
    typer.echo(f"symbol_{_SYMBOL}_resolves={str(result.symbol_resolves).lower()}")
    typer.echo(
        f"streamer_symbol_matches_{_EXPECTED_STREAMER}="
        f"{str(result.streamer_symbol_matches).lower()}"
    )
    typer.echo("quote_token_requested=false")
    typer.echo(f"PREFLIGHT_RESULT={'PASS' if result.ok else 'FAIL'}")
    if not result.ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
