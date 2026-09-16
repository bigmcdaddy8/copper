"""0W-4B: generalized ES quarterly-contract resolution/validation.

Before 0W-4B, the collector hard-rejected everything except the literal
string `/ESU6`. That is unsafe once the pinned contract must change (a roll
or expiration). These tests prove the generalized `resolve_es_contract` still
authoritatively verifies against futures metadata -- never DXLink -- while
accepting any recognized ES quarterly contract, and that preflight and the
collector cannot independently drift onto different contracts.
"""
from __future__ import annotations

import pytest

from dicks_laboratory.es_contract import (
    EsContractResolutionError,
    expected_streamer_symbol,
    resolve_es_contract,
)
from dicks_laboratory.production_symbol import PINNED_ES_SYMBOL

_DEC_2026 = {
    "symbol": "/ESZ6",
    "streamer-symbol": "/ESZ26:XCME",
    "product-code": "ES",
    "is-tradeable": True,
    "expiration-date": "2026-12-18",
}
_SEP_2026_ROLLED_OFF = {
    "symbol": "/ESU6",
    "streamer-symbol": "/ESU26:XCME",
    "product-code": "ES",
    "is-tradeable": True,
    "expiration-date": "2026-09-18",
}


class _Client:
    def __init__(self, futures):
        self._futures = futures

    def list_futures(self):
        return self._futures


# --- A. valid new ES quarterly contract accepted ----------------------------


def test_resolves_valid_december_contract_with_correct_mapping():
    contract = resolve_es_contract(_Client([_DEC_2026]), "/ESZ6")
    assert contract.streamer_symbol == "/ESZ26:XCME"
    assert contract.instrument.canonical_id == "FUTURE:CME:ES:2026-12"
    assert contract.expiration_date == "2026-12-18"


def test_pinned_production_symbol_is_december_2026():
    # 0W-4B: the September contract expired/rolled 2026-09-18/14; the
    # production pin must not still point at it.
    assert PINNED_ES_SYMBOL == "/ESZ6"


# --- B. historical September contract remains independently resolvable -----


def test_historical_september_contract_still_resolves_on_its_own_metadata():
    # Historical datasets recorded FUTURE:CME:ES:2026-09 identity. This proves
    # that identity is still independently derivable/valid -- production
    # selection simply no longer defaults to it.
    contract = resolve_es_contract(_Client([_SEP_2026_ROLLED_OFF]), "/ESU6")
    assert contract.instrument.canonical_id == "FUTURE:CME:ES:2026-09"


# --- C. non-ES symbol rejected ----------------------------------------------


def test_rejects_non_es_symbol():
    futures = [{"symbol": "/CLZ6", "streamer-symbol": "/CLZ26:XNYM", "product-code": "CL", "is-tradeable": True}]
    with pytest.raises(EsContractResolutionError):
        resolve_es_contract(_Client(futures), "/CLZ6")


def test_rejects_symbol_with_es_prefix_but_wrong_product_code():
    # e.g. a mislabeled/synthetic metadata row -- product-code is authoritative.
    futures = [{"symbol": "/ESZ6", "streamer-symbol": "/ESZ26:XCME", "product-code": "MES", "is-tradeable": True}]
    with pytest.raises(EsContractResolutionError):
        resolve_es_contract(_Client(futures), "/ESZ6")


# --- D. unresolved ES-like symbol rejected ----------------------------------


def test_rejects_unresolved_symbol():
    with pytest.raises(EsContractResolutionError):
        resolve_es_contract(_Client([_DEC_2026]), "/ESH7")  # not in the fake metadata


def test_rejects_malformed_symbol():
    with pytest.raises(EsContractResolutionError):
        resolve_es_contract(_Client([_DEC_2026]), "/ESZZ")


def test_rejects_untradeable_contract():
    futures = [{**_DEC_2026, "is-tradeable": False}]
    with pytest.raises(EsContractResolutionError):
        resolve_es_contract(_Client(futures), "/ESZ6")


# --- E. streamer mismatch rejected ------------------------------------------


def test_rejects_streamer_symbol_mismatch():
    futures = [{**_DEC_2026, "streamer-symbol": "/ESU26:XCME"}]
    with pytest.raises(EsContractResolutionError):
        resolve_es_contract(_Client(futures), "/ESZ6")


def test_expected_streamer_symbol_helper():
    assert expected_streamer_symbol("/ESZ6") == "/ESZ26:XCME"
    assert expected_streamer_symbol("/ESU6") == "/ESU26:XCME"
    assert expected_streamer_symbol("/ESH7") == "/ESH27:XCME"
    with pytest.raises(EsContractResolutionError):
        expected_streamer_symbol("/NQZ6")


# --- F. preflight / collector configuration agreement -----------------------


def test_preflight_script_and_collector_script_share_pinned_symbol():
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    preflight_src = (repo_root / "scripts" / "dicks_lab_preflight.py").read_text()
    collector_src = (repo_root / "scripts" / "dicks_lab_collect_es.py").read_text()
    assert "from dicks_laboratory.production_symbol import PINNED_ES_SYMBOL" in preflight_src
    assert "from dicks_laboratory.production_symbol import PINNED_ES_SYMBOL" in collector_src
    unit_path = repo_root / "deploy" / "dicks_laboratory" / "systemd" / "dicks-lab-es-session.service"
    (exec_line,) = (line for line in unit_path.read_text().splitlines() if line.startswith("ExecStart="))
    assert f"--symbol {PINNED_ES_SYMBOL}" in exec_line


# --- G. new-contract dataset provenance -------------------------------------


def test_new_contract_produces_correct_provenance_identity():
    contract = resolve_es_contract(_Client([_DEC_2026]), "/ESZ6")
    assert contract.instrument.exchange == "CME"
    assert contract.instrument.root == "ES"
    assert contract.instrument.expiration_year == 2026
    assert contract.instrument.expiration_month == 12
    # Source-locator convention used by the collector for its dataset record.
    source_locator = f"TASTYTRADE_DXLINK:{contract.streamer_symbol}:TimeAndSale"
    assert source_locator == "TASTYTRADE_DXLINK:/ESZ26:XCME:TimeAndSale"
