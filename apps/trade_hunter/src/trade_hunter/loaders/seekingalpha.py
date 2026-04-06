import io
import re
import zipfile
from pathlib import Path

import pandas as pd

BULL_GLOB = "Copper_BULLish *.xlsx"
BEAR_GLOB = "Copper_BEARish *.xlsx"

REQUIRED_COLUMNS = ["Symbol", "Quant Rating", "Growth", "Momentum"]

_OUTPUT_COLUMNS = [
    "Symbol",
    "Company Name",
    "Quant Rating",
    "Growth",
    "Momentum",
    "Upcoming Announce Date",
]


_CF_PATTERN = re.compile(rb"<conditionalFormatting\b[^>]*>.*?</conditionalFormatting>", re.DOTALL)


def _read_xlsx_tolerant(path: Path) -> pd.DataFrame:
    """Read a SeekingAlpha xlsx, stripping conditional-formatting rules that
    openpyxl cannot parse (e.g. the 'notContainsBlanks' operator)."""
    with zipfile.ZipFile(path, "r") as zin:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                content = zin.read(item.filename)
                if item.filename.startswith("xl/worksheets/") and item.filename.endswith(".xml"):
                    content = _CF_PATTERN.sub(b"", content)
                zout.writestr(item, content)
        buf.seek(0)
        return pd.read_excel(buf, engine="openpyxl")


def discover_seekingalpha_file(downloads_dir: Path, glob: str) -> Path:
    """Return the newest SeekingAlpha Excel file in downloads_dir matching glob.

    'Newest' is the file whose YYYY-MM-DD suffix (the final space-delimited segment
    of the stem) sorts highest lexicographically.

    Raises:
        FileNotFoundError: if no matching file is found.
    """
    candidates = list(downloads_dir.glob(glob))
    if not candidates:
        raise FileNotFoundError(
            f"No SeekingAlpha file found in '{downloads_dir}' matching pattern: {glob}"
        )
    return max(candidates, key=lambda p: p.stem.split(" ")[-1])


def load_seekingalpha(
    downloads_dir: Path,
    explicit_path: Path | None = None,
    side: str = "BULL",
) -> tuple[pd.DataFrame, list[str]]:
    """Load a SeekingAlpha Excel file and return (DataFrame, warnings).

    If explicit_path is provided it is used directly; otherwise the appropriate
    glob (BULL_GLOB or BEAR_GLOB) is used for discovery based on side.

    Args:
        downloads_dir: Directory to search when explicit_path is None.
        explicit_path: Use this file directly instead of discovering.
        side: "BULL" or "BEAR" — selects the discovery glob and labels warnings.

    Raises:
        FileNotFoundError: if explicit_path does not exist, or discovery finds no files.
        ValueError: if any required column is missing from the file.
    """
    warnings: list[str] = []
    label = f"SeekingAlpha {side}"

    if explicit_path is not None:
        if not explicit_path.exists():
            raise FileNotFoundError(f"{label} file not found: {explicit_path}")
        path = explicit_path
    else:
        glob = BULL_GLOB if side == "BULL" else BEAR_GLOB
        path = discover_seekingalpha_file(downloads_dir, glob)

    df = _read_xlsx_tolerant(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{label} file missing required columns: {missing}")

    # Drop rows with null/empty Symbol
    null_mask = df["Symbol"].isna() | (df["Symbol"].astype(str).str.strip() == "")
    if null_mask.any():
        warnings.append(f"[{label}] {null_mask.sum()} row(s) with null/empty Symbol dropped")
        df = df[~null_mask].copy()

    df["Symbol"] = df["Symbol"].astype(str).str.strip()

    available = [c for c in _OUTPUT_COLUMNS if c in df.columns]
    return df[available].reset_index(drop=True), warnings
