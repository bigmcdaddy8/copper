"""Pre-arm credential + instrument preflight for long-horizon ES capture.

0W-2D: proves OAuth/REST reachability, the futures endpoint, and that the
pinned contract resolves to its streamer symbol -- WITHOUT requesting a DXLink
quote token. 0X-A adds the contract-roll status of the pin (warn-only while
approaching/due; fail-closed when stale, invalid or conflicted). Requesting
the quote token early starts its ~24h lifetime and was the 0W-2 Attempt-3
KNOWN_GAP root cause (see docs/dicks_laboratory 0W-2C / 0W-2D). Prints only
booleans / counts. Exit 0 = PASS.

Run this at arming time; run `dicks_lab_collect_es.py` (which obtains the quote
token at startup) at the actual session launch.
"""
from __future__ import annotations

from datetime import datetime, timezone

import typer
from dotenv import load_dotenv

from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.settings import TastytradeSettings
from dicks_laboratory.es_contract import expected_streamer_symbol
from dicks_laboratory.futures_contracts import RollSeverity, assess_roll, upcoming_trading_date
from dicks_laboratory.preflight import run_credential_preflight
from dicks_laboratory.production_symbol import PINNED_ES_SYMBOL

app = typer.Typer(add_completion=False)
# 0W-4B: single source of truth shared with dicks_lab_collect_es.py, so
# preflight and the collector can never validate different contracts.
_SYMBOL = PINNED_ES_SYMBOL
_EXPECTED_STREAMER = expected_streamer_symbol(_SYMBOL)


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
    # 0X-A: contract-roll status of the pin for the trading date this preflight
    # protects, from the same metadata response. ROLL_APPROACHING / ROLL_DUE
    # warn only; a stale, invalid or conflicted pin fails closed. Never re-pins.
    roll = assess_roll(result.futures_metadata, _SYMBOL, upcoming_trading_date(datetime.now(tz=timezone.utc)))
    typer.echo(f"roll_trading_date={roll.trading_date.isoformat()}")
    typer.echo(f"roll_state={roll.state.value} roll_severity={roll.severity.value}")
    for reason in roll.reasons:
        typer.echo(f"roll_reason={reason}")
    typer.echo(f"roll_recommended_action={roll.recommended_action}")
    typer.echo("quote_token_requested=false")
    ok = result.ok and roll.severity is not RollSeverity.FAIL
    typer.echo(f"PREFLIGHT_RESULT={'PASS' if ok else 'FAIL'}")
    if not ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
