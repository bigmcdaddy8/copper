from pathlib import Path

import pandas as pd

from trade_hunter.pipeline.normalize import SECTOR_MAP, assign_bucket

REQUIRED_COLUMNS = ["Symbol", "IV Idx", "IV Rank", "IV %tile", "Sector"]

TASTYTRADE_GLOB = "tastytrade_watchlist_m8investments_Russell 1000_*.csv"

_OUTPUT_COLUMNS = [
    "Symbol",
    "Name",
    "Liquidity",
    "IV Idx",
    "IV Rank",
    "IV %tile",
    "Earnings At",
    "Sector",
    "Sector Bucket",
]


def discover_tastytrade_file(downloads_dir: Path) -> Path:
    """Return the newest TastyTrade CSV in downloads_dir matched by TASTYTRADE_GLOB.

    'Newest' is the file whose YYMMDD suffix (the final underscore-delimited segment
    of the stem) sorts highest lexicographically.

    Raises:
        FileNotFoundError: if no matching file is found.
    """
    candidates = list(downloads_dir.glob(TASTYTRADE_GLOB))
    if not candidates:
        raise FileNotFoundError(
            f"No TastyTrade file found in '{downloads_dir}' matching pattern: {TASTYTRADE_GLOB}"
        )
    return max(candidates, key=lambda p: p.stem.split("_")[-1])


def load_tastytrade(
    downloads_dir: Path,
    explicit_path: Path | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Load TastyTrade CSV and return the Universal Data Set plus a list of warnings.

    If explicit_path is provided it is used directly; otherwise the newest matching
    file in downloads_dir is discovered automatically.

    Raises:
        FileNotFoundError: if explicit_path does not exist, or discovery finds no files.
        ValueError: if any required column is missing from the file.
    """
    warnings: list[str] = []

    if explicit_path is not None:
        if not explicit_path.exists():
            raise FileNotFoundError(f"TastyTrade file not found: {explicit_path}")
        path = explicit_path
    else:
        path = discover_tastytrade_file(downloads_dir)

    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"TastyTrade file missing required columns: {missing}")

    # Drop rows with null/empty Symbol
    null_mask = df["Symbol"].isna() | (df["Symbol"].astype(str).str.strip() == "")
    if null_mask.any():
        warnings.append(f"[TastyTrade] {null_mask.sum()} row(s) with null/empty Symbol dropped")
        df = df[~null_mask].copy()

    df["Symbol"] = df["Symbol"].astype(str).str.strip()

    # Normalize sectors; drop rows with unrecognized values
    df["Sector"] = df["Sector"].astype(str).str.strip()
    df["_std_sector"] = df["Sector"].map(SECTOR_MAP)
    unknown_mask = df["_std_sector"].isna()
    if unknown_mask.any():
        for _, row in df[unknown_mask].iterrows():
            warnings.append(
                f"[TastyTrade] Unknown sector '{row['Sector']}' for '{row['Symbol']}' — skipped"
            )
        df = df[~unknown_mask].copy()

    df["Sector"] = df["_std_sector"]
    df = df.drop(columns=["_std_sector"])
    df["Sector Bucket"] = df["Sector"].map(assign_bucket)

    # Normalize numeric IV columns:
    #   IV Idx  — strip "%" suffix and commas, convert to float (NaN for "--" / missing)
    #   IV Rank — convert to float (NaN for "--" / missing)
    #   IV %tile — convert to float (NaN for "--" / missing)
    for col in ("IV Idx",):
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.rstrip("%")
                .replace({"--": None, "nan": None, "": None})
                .astype(float)
            )
    for col in ("IV Rank", "IV %tile"):
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .replace({"--": None, "nan": None, "": None})
                .astype(float)
            )

    available = [c for c in _OUTPUT_COLUMNS if c in df.columns]
    return df[available].reset_index(drop=True), warnings
