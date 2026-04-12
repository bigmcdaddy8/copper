from __future__ import annotations
import json
import shutil
from datetime import date as _date_type, datetime, timedelta
import typer
from rich.console import Console
from rich.table import Table
from bic.models import OHLCVBar

app = typer.Typer()
console = Console()

_SCENARIOS = {
    "immediate-fill": "scenario_immediate_fill",
    "no-fill-timeout": "scenario_no_fill_timeout",
    "entry-tp": "scenario_entry_then_tp",
    "entry-expire-profit": "scenario_entry_expire_profit",
    "entry-expire-loss": "scenario_entry_expire_loss",
    "account-minimum-block": "scenario_account_minimum_block",
    "existing-position-block": "scenario_existing_position_block",
}


@app.callback()
def main() -> None:
    """holodeck — SPX simulation broker for K9 development."""


@app.command(name="generate-data")
def generate_data(
    output: str = typer.Option(
        "data/holodeck/spx_2026_01_minutes.csv",
        help="Output path for synthetic SPX CSV (relative to cwd).",
    ),
    seed: int = typer.Option(42, help="Random seed for deterministic generation."),
) -> None:
    """Generate synthetic SPX minute-bar data for January 2026."""
    from holodeck.market_data import generate_spx_minutes

    console.print(
        f"Generating synthetic SPX minute data for January 2026 → [bold]{output}[/bold]"
    )
    generate_spx_minutes(seed=seed, output_path=output)
    row_count = sum(1 for _ in open(output)) - 1  # subtract header
    console.print(f"[bold green]Done.[/bold green] {row_count:,} bars written to {output}")


@app.command(name="run-scenario")
def run_scenario(
    name: str = typer.Option(..., help=f"Scenario name. One of: {', '.join(_SCENARIOS)}"),
    output: str = typer.Option(
        "data/holodeck/spx_2026_01_minutes.csv",
        help="Path to synthetic SPX CSV.",
    ),
    seed: int = typer.Option(42, help="Random seed (must match generate-data seed)."),
) -> None:
    """Run a named deterministic test scenario against Holodeck."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from holodeck.broker import HolodeckBroker
    from holodeck.config import HolodeckConfig
    import holodeck.scenarios.spx_0dte as _mod

    if name not in _SCENARIOS:
        console.print(f"[bold red]Unknown scenario: {name!r}[/bold red]")
        console.print(f"Available: {', '.join(_SCENARIOS)}")
        raise typer.Exit(1)

    TZ = "America/Chicago"
    config = HolodeckConfig(
        starting_datetime=datetime(2026, 1, 2, 10, 0, tzinfo=ZoneInfo(TZ)),
        ending_datetime=datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ)),
        random_seed=seed,
        data_path=output,
    )
    broker = HolodeckBroker(config)
    fn = getattr(_mod, _SCENARIOS[name])

    console.print(f"Running scenario: [bold]{name}[/bold]")
    try:
        result = fn(broker)
    except Exception as e:
        console.print(f"[bold red]Scenario failed: {e}[/bold red]")
        raise typer.Exit(1)

    console.print_json(json.dumps(result))

    # Exit 1 if any boolean value in result is False (scenario assertion failure)
    failed = [k for k, v in result.items() if isinstance(v, bool) and not v]
    if failed:
        console.print(f"[bold red]Assertions failed: {failed}[/bold red]")
        raise typer.Exit(1)
    console.print("[bold green]Scenario passed.[/bold green]")


@app.command(name="option-chain")
def option_chain(
    symbol: str = typer.Option("SPX", help="Underlying symbol (only SPX supported)."),
    date_str: str = typer.Option(
        ..., "--date", help="As-of date (YYYY-MM-DD).  Must be a Jan 2026 trading day."
    ),
    time_str: str = typer.Option(
        "09:30", "--time", help="As-of time in CT (HH:MM, 24h).  Defaults to market open."
    ),
    expiration_str: str = typer.Option(
        ..., "--expiration", help="Option expiration date (YYYY-MM-DD)."
    ),
    data: str = typer.Option(
        "data/holodeck/spx_2026_01_minutes.csv",
        help="Path to synthetic SPX CSV.",
    ),
    window: int = typer.Option(
        100, help="Show strikes within ±N points of ATM (default 100)."
    ),
) -> None:
    """Display an option chain for a given date, time, and expiration."""
    from datetime import datetime, date as _date
    from zoneinfo import ZoneInfo
    from holodeck.broker import HolodeckBroker
    from holodeck.config import HolodeckConfig

    TZ = "America/Chicago"
    tz = ZoneInfo(TZ)

    try:
        trade_date = _date.fromisoformat(date_str)
        hour, minute = (int(p) for p in time_str.split(":"))
        as_of_dt = datetime(trade_date.year, trade_date.month, trade_date.day, hour, minute, tzinfo=tz)
        expiration = _date.fromisoformat(expiration_str)
    except ValueError as exc:
        console.print(f"[bold red]Invalid date/time: {exc}[/bold red]")
        raise typer.Exit(1)

    config = HolodeckConfig(
        starting_datetime=as_of_dt,
        ending_datetime=datetime(trade_date.year, trade_date.month, trade_date.day, 15, 0, tzinfo=tz),
        data_path=data,
    )

    try:
        broker = HolodeckBroker(config)
    except FileNotFoundError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(1)

    try:
        quote = broker.get_underlying_quote(symbol)
        chain = broker.get_option_chain(symbol, expiration)
    except (KeyError, ValueError) as exc:
        console.print(f"[bold red]Data error: {exc}[/bold red]")
        console.print("[dim]Hint: Holodeck synthetic data covers Jan 2–30 2026 only.[/dim]")
        raise typer.Exit(1)

    underlying = quote.last
    atm_strike = round(underlying / 5) * 5

    # Split into calls and puts, keyed by strike
    calls: dict[float, object] = {}
    puts: dict[float, object] = {}
    for opt in chain.options:
        if opt.option_type == "CALL":
            calls[opt.strike] = opt
        else:
            puts[opt.strike] = opt

    strikes = sorted(
        s for s in set(calls) | set(puts)
        if abs(s - underlying) <= window
    )

    # Build Rich table
    table = Table(
        title=f"{symbol}  {expiration}  │  as-of {date_str} {time_str} CT  │  underlying {underlying:.2f}",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Strike", justify="right", style="white")
    table.add_column("Call Bid", justify="right")
    table.add_column("Call Ask", justify="right")
    table.add_column("Call Δ", justify="right")
    table.add_column("", justify="center")   # ATM marker
    table.add_column("Put Bid", justify="right")
    table.add_column("Put Ask", justify="right")
    table.add_column("Put Δ", justify="right")

    for strike in strikes:
        is_atm = abs(strike - atm_strike) < 3
        row_style = "bold yellow" if is_atm else ""
        marker = "◄ ATM" if is_atm else ""

        call = calls.get(strike)
        put = puts.get(strike)

        c_bid = f"{call.bid:.2f}" if call else "—"
        c_ask = f"{call.ask:.2f}" if call else "—"
        c_delta = f"{call.delta:+.2f}" if call else "—"
        p_bid = f"{put.bid:.2f}" if put else "—"
        p_ask = f"{put.ask:.2f}" if put else "—"
        p_delta = f"{put.delta:+.2f}" if put else "—"

        table.add_row(
            f"{strike:.0f}", c_bid, c_ask, c_delta, marker, p_bid, p_ask, p_delta,
            style=row_style,
        )

    console.print(table)
    console.print(
        f"[dim]{len(strikes)} strikes shown  ·  ±{window}pt window  ·  "
        f"{len(chain.options)} total contracts in chain[/dim]"
    )


def _flat_bar(symbol: str, timestamp: datetime, price: float) -> OHLCVBar:
    """Return a zero-height bar used to mark a non-trading gap."""
    return OHLCVBar(
        symbol=symbol, timestamp=timestamp,
        open=price, high=price, low=price, close=price,
    )


_RESOLUTION_MINUTES: dict[str, int] = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "1d": 1440, "1w": 10080,
}


def _insert_gap_bars(bars: list[OHLCVBar], resolution: str) -> list[OHLCVBar]:
    """Insert flat gap bars at weekend / overnight breaks for visual separation.

    1w  — inserts Sat + Sun flat bars between each pair of weekly bars.
    1d  — inserts one flat bar per missing calendar day between daily bars.
    sub-daily — inserts one flat bar between each pair of bars from different trading days.
    1M  — no gap insertion.
    """
    if len(bars) < 2 or resolution == "1M" or resolution not in _RESOLUTION_MINUTES:
        return bars

    interval_min = _RESOLUTION_MINUTES[resolution]
    result: list[OHLCVBar] = []

    for i, bar in enumerate(bars):
        result.append(bar)
        if i == len(bars) - 1:
            break
        next_bar = bars[i + 1]
        gap_sec = (next_bar.timestamp - bar.timestamp).total_seconds()
        if gap_sec <= interval_min * 60 * 1.5:
            continue  # consecutive bars — no gap needed

        close_price = bar.close
        if resolution == "1d":
            day = bar.timestamp + timedelta(days=1)
            while day.date() < next_bar.timestamp.date():
                result.append(_flat_bar(bar.symbol, day, close_price))
                day += timedelta(days=1)
        elif resolution == "1w":
            sat = next_bar.timestamp - timedelta(days=2)
            sun = next_bar.timestamp - timedelta(days=1)
            result.append(_flat_bar(bar.symbol, sat, close_price))
            result.append(_flat_bar(bar.symbol, sun, close_price))
        else:  # sub-daily
            gap_ts = bar.timestamp + timedelta(minutes=interval_min)
            result.append(_flat_bar(bar.symbol, gap_ts, close_price))

    return result


@app.command(name="chart-bars")
def chart_bars(
    symbol: str = typer.Option("SPX", help="Underlying symbol (only SPX supported)."),
    start: str = typer.Option(
        ..., "--start", help="Start date, inclusive (YYYY-MM-DD).  Must be a Jan 2026 trading day."
    ),
    end: str = typer.Option(
        ..., "--end", help="End date, inclusive (YYYY-MM-DD).  Must be a Jan 2026 trading day."
    ),
    resolution: str = typer.Option(
        "1d", help="Bar resolution: 1m, 5m, 15m, 30m, 1h, 1d, 1w, 1M."
    ),
    dark: bool = typer.Option(
        False, "--dark", help="Use dark theme (dark background, light axes and legend)."
    ),
    data: str = typer.Option(
        "data/holodeck/spx_2026_01_minutes.csv",
        help="Path to synthetic SPX CSV.",
    ),
) -> None:
    """Render a terminal candlestick chart for a date range and resolution."""
    import plotext as plt
    from datetime import datetime, date as _date
    from zoneinfo import ZoneInfo
    from holodeck.broker import HolodeckBroker
    from holodeck.config import HolodeckConfig

    TZ = "America/Chicago"
    tz = ZoneInfo(TZ)

    try:
        start_date = _date.fromisoformat(start)
        end_date = _date.fromisoformat(end)
    except ValueError as exc:
        console.print(f"[bold red]Invalid date: {exc}[/bold red]")
        raise typer.Exit(1)

    if end_date < start_date:
        console.print("[bold red]--end must be >= --start[/bold red]")
        raise typer.Exit(1)

    valid_resolutions = {"1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M"}
    if resolution not in valid_resolutions:
        console.print(f"[bold red]Invalid resolution {resolution!r}. Must be one of: {', '.join(sorted(valid_resolutions))}[/bold red]")
        raise typer.Exit(1)

    start_dt = datetime(start_date.year, start_date.month, start_date.day, 9, 30, tzinfo=tz)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 15, 0, tzinfo=tz)

    config = HolodeckConfig(
        starting_datetime=start_dt,
        ending_datetime=end_dt,
        data_path=data,
    )

    try:
        broker = HolodeckBroker(config)
    except FileNotFoundError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(1)

    try:
        bars = broker.get_ohlcv_bars(symbol, start_dt, end_dt, resolution)
    except (KeyError, ValueError) as exc:
        console.print(f"[bold red]Data error: {exc}[/bold red]")
        console.print("[dim]Hint: Holodeck synthetic data covers Jan 2–30 2026 only.[/dim]")
        raise typer.Exit(1)

    bars = _insert_gap_bars(bars, resolution)

    if not bars:
        console.print("[yellow]No bars found for the given range.[/yellow]")
        raise typer.Exit(0)

    # Index-based positioning: sequential fake dates so bars are equidistant
    # regardless of calendar gaps (weekends, holidays).  Real timestamps are
    # applied as x-axis tick labels via plt.xticks().
    _epoch = _date_type(2000, 1, 1)
    fake_dates = [
        (_epoch + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(len(bars))
    ]

    # Real label format depends on resolution (intraday shows time component)
    if resolution in ("1m", "5m", "15m", "30m", "1h"):
        real_labels = [b.timestamp.strftime("%Y-%m-%d %H:%M") for b in bars]
    else:
        real_labels = [b.timestamp.strftime("%Y-%m-%d") for b in bars]

    # Thin tick positions to ~8 labels max to avoid crowding on narrow terminals
    tick_count = min(8, len(bars))
    step = max(1, len(bars) // tick_count)
    tick_indices = list(range(0, len(bars), step))
    tick_positions = [fake_dates[i] for i in tick_indices]
    tick_labels = [real_labels[i] for i in tick_indices]

    ohlc = {
        "Open":  [b.open  for b in bars],
        "High":  [b.high  for b in bars],
        "Low":   [b.low   for b in bars],
        "Close": [b.close for b in bars],
    }

    term_w = shutil.get_terminal_size(fallback=(80, 24)).columns
    plot_w = min(term_w, max(60, len(bars) * 8))

    plt.clf()
    if dark:
        plt.theme("dark")
    plt.plotsize(plot_w, None)
    plt.date_form("Y-m-d")
    plt.candlestick(fake_dates, ohlc, colors=["red", "green"])
    plt.xticks(tick_positions, tick_labels)
    plt.title(f"{symbol}  {start} → {end}  ({resolution})")
    plt.ylabel("Price")
    plt.show()

    console.print(
        f"[dim]{len(bars)} bars  ·  resolution {resolution}  ·  "
        f"{start} → {end}[/dim]"
    )


@app.command(name="live-bars")
def live_bars(
    symbol: str = typer.Option("SPX", help="Underlying symbol (only SPX supported)."),
    start: str = typer.Option(
        ..., "--start", help="Start date, inclusive (YYYY-MM-DD).  Must be a Jan 2026 trading day."
    ),
    end: str = typer.Option(
        ..., "--end", help="End date, inclusive (YYYY-MM-DD).  Must be a Jan 2026 trading day."
    ),
    resolution: str = typer.Option(
        "1d", help="Bar resolution: 1m, 5m, 15m, 30m, 1h, 1d, 1w, 1M."
    ),
    speed: str = typer.Option(
        "5m", "--speed",
        help="Virtual time per real second: 1m, 5m, 15m, 30m, 1h, 1d.",
    ),
    dark: bool = typer.Option(False, "--dark", help="Use dark theme."),
    data: str = typer.Option(
        "data/holodeck/spx_2026_01_minutes.csv",
        help="Path to synthetic SPX CSV.",
    ),
) -> None:
    """Stream a live-updating candlestick chart driven by virtual time."""
    import plotext as plt
    from zoneinfo import ZoneInfo
    from rich.live import Live
    from rich.text import Text
    from holodeck.broker import HolodeckBroker
    from holodeck.config import HolodeckConfig
    from holodeck.live_loop import LiveLoop, SPEED_MINUTES

    TZ = "America/Chicago"
    tz = ZoneInfo(TZ)

    try:
        start_date = _date_type.fromisoformat(start)
        end_date   = _date_type.fromisoformat(end)
    except ValueError as exc:
        console.print(f"[bold red]Invalid date: {exc}[/bold red]")
        raise typer.Exit(1)

    if end_date < start_date:
        console.print("[bold red]--end must be >= --start[/bold red]")
        raise typer.Exit(1)

    valid_resolutions = {"1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M"}
    if resolution not in valid_resolutions:
        console.print(f"[bold red]Invalid resolution {resolution!r}.[/bold red]")
        raise typer.Exit(1)

    if speed not in SPEED_MINUTES:
        console.print(
            f"[bold red]Invalid speed {speed!r}.  Valid: {sorted(SPEED_MINUTES)}[/bold red]"
        )
        raise typer.Exit(1)

    start_dt = datetime(start_date.year, start_date.month, start_date.day, 9, 30, tzinfo=tz)
    end_dt   = datetime(end_date.year,   end_date.month,   end_date.day,  15,  0, tzinfo=tz)

    config = HolodeckConfig(
        starting_datetime=start_dt,
        ending_datetime=end_dt,
        data_path=data,
    )

    try:
        broker = HolodeckBroker(config)
    except FileNotFoundError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(1)

    def _render(vtime: datetime) -> Text:
        try:
            bars = broker.get_ohlcv_bars(symbol, start_dt, vtime, resolution)
        except (KeyError, ValueError):
            return Text("(no data)")

        bars = _insert_gap_bars(bars, resolution)
        if not bars:
            return Text("(no bars yet)")

        # Rolling window: always show the last N bars so newest is pinned to right
        term_w = shutil.get_terminal_size(fallback=(80, 24)).columns
        n_visible = max(4, int(term_w / 2))
        bars = bars[-n_visible:]

        epoch = _date_type(2000, 1, 1)
        fake_dates = [
            (epoch + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(len(bars))
        ]
        if resolution in ("1m", "5m", "15m", "30m", "1h"):
            real_labels = [b.timestamp.strftime("%Y-%m-%d %H:%M") for b in bars]
        else:
            real_labels = [b.timestamp.strftime("%Y-%m-%d") for b in bars]

        tick_count = min(8, len(bars))
        step = max(1, len(bars) // tick_count)
        tick_positions = [fake_dates[i] for i in range(0, len(bars), step)]
        tick_labels    = [real_labels[i] for i in range(0, len(bars), step)]

        ohlc = {
            "Open":  [b.open  for b in bars],
            "High":  [b.high  for b in bars],
            "Low":   [b.low   for b in bars],
            "Close": [b.close for b in bars],
        }

        plt.clf()
        if dark:
            plt.theme("dark")
        plt.plotsize(term_w, None)
        plt.date_form("Y-m-d")
        plt.candlestick(fake_dates, ohlc, colors=["red", "green"])
        plt.xticks(tick_positions, tick_labels)
        plt.title(
            f"{symbol}  {start} → {vtime.strftime('%Y-%m-%d %H:%M')} CT  ({resolution})"
        )
        plt.ylabel("Price")
        return Text.from_ansi(plt.build())

    loop = LiveLoop(broker._clock, speed=speed, data_end=end_dt)

    console.print(
        f"[dim]live-bars  {symbol}  {start} → {end}  "
        f"resolution={resolution}  speed={speed}  (Ctrl+C to quit)[/dim]"
    )

    try:
        with Live(Text(""), refresh_per_second=2, transient=False) as live:
            for vtime in loop:
                live.update(_render(vtime))
    except KeyboardInterrupt:
        pass

    console.print("[dim]live-bars stopped.[/dim]")


@app.command(name="live-chain")
def live_chain(
    symbol: str = typer.Option("SPX", help="Underlying symbol (only SPX supported)."),
    date_str: str = typer.Option(
        ..., "--date", help="Trading date (YYYY-MM-DD).  Must be a Jan 2026 trading day."
    ),
    expiration_str: str = typer.Option(
        ..., "--expiration", help="Option expiration date (YYYY-MM-DD)."
    ),
    speed: str = typer.Option(
        "5m", "--speed",
        help="Virtual time per real second: 1m, 5m, 15m, 30m, 1h, 1d.",
    ),
    data: str = typer.Option(
        "data/holodeck/spx_2026_01_minutes.csv",
        help="Path to synthetic SPX CSV.",
    ),
    window: int = typer.Option(100, help="Show strikes within ±N points of ATM (default 100)."),
) -> None:
    """Stream a live-updating option chain table driven by virtual time."""
    from zoneinfo import ZoneInfo
    from rich.live import Live
    from holodeck.broker import HolodeckBroker
    from holodeck.config import HolodeckConfig
    from holodeck.live_loop import LiveLoop, SPEED_MINUTES

    TZ = "America/Chicago"
    tz = ZoneInfo(TZ)

    try:
        trade_date = _date_type.fromisoformat(date_str)
        expiration = _date_type.fromisoformat(expiration_str)
    except ValueError as exc:
        console.print(f"[bold red]Invalid date: {exc}[/bold red]")
        raise typer.Exit(1)

    if speed not in SPEED_MINUTES:
        console.print(
            f"[bold red]Invalid speed {speed!r}.  Valid: {sorted(SPEED_MINUTES)}[/bold red]"
        )
        raise typer.Exit(1)

    start_dt = datetime(trade_date.year, trade_date.month, trade_date.day, 9, 30, tzinfo=tz)
    end_dt   = datetime(trade_date.year, trade_date.month, trade_date.day, 15,  0, tzinfo=tz)

    config = HolodeckConfig(
        starting_datetime=start_dt,
        ending_datetime=end_dt,
        data_path=data,
    )

    try:
        broker = HolodeckBroker(config)
    except FileNotFoundError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(1)

    def _render(vtime: datetime) -> Table:
        try:
            quote = broker.get_underlying_quote(symbol)
            chain = broker.get_option_chain(symbol, expiration)
        except (KeyError, ValueError):
            t = Table(title=f"{symbol}  {expiration}  │  {vtime.strftime('%H:%M')} CT")
            t.add_column("Status")
            t.add_row("[yellow]no data[/yellow]")
            return t

        underlying = quote.last
        atm_strike = round(underlying / 5) * 5

        calls: dict[float, object] = {}
        puts:  dict[float, object] = {}
        for opt in chain.options:
            if opt.option_type == "CALL":
                calls[opt.strike] = opt
            else:
                puts[opt.strike]  = opt

        strikes = sorted(
            s for s in set(calls) | set(puts)
            if abs(s - underlying) <= window
        )

        table = Table(
            title=(
                f"{symbol}  {expiration}  │  "
                f"{vtime.strftime('%Y-%m-%d %H:%M')} CT  │  "
                f"underlying {underlying:.2f}"
            ),
            show_header=True,
            header_style="bold",
        )
        table.add_column("Strike",   justify="right", style="white")
        table.add_column("Call Bid", justify="right")
        table.add_column("Call Ask", justify="right")
        table.add_column("Call Δ",   justify="right")
        table.add_column("",         justify="center")
        table.add_column("Put Bid",  justify="right")
        table.add_column("Put Ask",  justify="right")
        table.add_column("Put Δ",    justify="right")

        for strike in strikes:
            is_atm = abs(strike - atm_strike) < 3
            marker = "◄ ATM" if is_atm else ""
            row_style = "bold yellow" if is_atm else ""

            call = calls.get(strike)
            put  = puts.get(strike)

            c_bid   = f"{call.bid:.2f}"    if call else "—"
            c_ask   = f"{call.ask:.2f}"    if call else "—"
            c_delta = f"{call.delta:+.2f}" if call else "—"
            p_bid   = f"{put.bid:.2f}"     if put  else "—"
            p_ask   = f"{put.ask:.2f}"     if put  else "—"
            p_delta = f"{put.delta:+.2f}"  if put  else "—"

            table.add_row(
                f"{strike:.0f}", c_bid, c_ask, c_delta, marker, p_bid, p_ask, p_delta,
                style=row_style,
            )

        return table

    loop = LiveLoop(broker._clock, speed=speed, data_end=end_dt)

    console.print(
        f"[dim]live-chain  {symbol}  {date_str}  expiry={expiration_str}  "
        f"speed={speed}  (Ctrl+C to quit)[/dim]"
    )

    try:
        with Live(refresh_per_second=2, transient=False) as live:
            for vtime in loop:
                live.update(_render(vtime))
    except KeyboardInterrupt:
        pass

    console.print("[dim]live-chain stopped.[/dim]")

