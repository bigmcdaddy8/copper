"""The canonical Drysdale setup vocabulary the Tutor receives (0AC-A4): TUTOR_POC_SETUP_CATALOG_V1.

Nothing here is a new rule. Every name and condition is read from, or copied verbatim from, the frozen
DRYSDALE_SETUP_CANDIDATES_V1 implementation (dicks_laboratory.drysdale):

    families         dry.SetupFamily (4)                    PRICE_DISCOVERY_CONTINUATION, FADE_VALUE_AREA_EXTREME,
                                                            RETURN_TO_VALUE, VWAP_BOUNCE
    directions       price_action.Direction (2)             UP, DOWN      -> 8 directional variants
    titles           DRYSDALE_MODULE topics                 "Price Discovery Continuation", ...
    candidate policy dry.CANDIDATE_POLICY                   e.g. VWAP_BOUNCE_CANDIDATE_V1
    source criteria  dry.SOURCE_CRITERIA                    SOURCE SAYS (paraphrase of the Human's notes)
    conditions       the frozen _cond(...) texts            LABORATORY V1 TRAINING PROXY, per direction

The condition texts are the strings the frozen family functions write into each candidate's
`laboratory_rule`; tests compare them with candidates the frozen engine produces for all eight variants, so
a drift in either place fails the build. `meaning` is this POC's one-line reading of the frozen docstrings
(what UP / DOWN means for that family); it carries no rule.
"""
from __future__ import annotations

import hashlib

from dicks_laboratory import drysdale as dry
from dicks_laboratory.price_action import Direction
from dicks_laboratory.tutor_evidence import DRYSDALE_MODULE, canonical_json

CATALOG_VERSION = "TUTOR_POC_SETUP_CATALOG_V1"
FAMILIES = tuple(dry.SetupFamily)
DIRECTIONS = (Direction.UP, Direction.DOWN)
TITLES = dict(zip(FAMILIES, (t.title for t in DRYSDALE_MODULE.topics), strict=True))
SHORT = dict(dry._SHORT)

_UP, _DOWN = Direction.UP, Direction.DOWN


def _w(d: Direction, up: str, down: str) -> str:
    return up if d is _UP else down


def _conditions(family: dry.SetupFamily, d: Direction) -> tuple[tuple[str, str], ...]:
    """(policy id, Laboratory V1 rule) in condition order, exactly as the frozen family functions write them."""
    close = f"the next complete bar closes {_w(d, 'above', 'below')} its open and "
    if family is dry.SetupFamily.PRICE_DISCOVERY_CONTINUATION:
        return ((dry.BREAKOUT_POLICY, f"a complete 5m bar closes strictly {_w(d, 'above +', 'below -')}1 sigma "
                 "(Globex VWAP bands)"),
                (dry.ACCEPTANCE_POLICY, "two consecutive complete 5m closes strictly beyond the same 1 sigma boundary"),
                (dry.RETEST_POLICY, "a later bar of the outside episode trades at or through the broken boundary and "
                 "closes back outside"),
                (dry.CONFIRMATION_POLICY, close + _w(d, "above the retest bar high", "below the retest bar low")))
    if family is dry.SetupFamily.FADE_VALUE_AREA_EXTREME:  # DOWN fades the upper band, UP the lower band
        return ((dry.ACCEPTANCE_POLICY, "two consecutive complete 5m closes inside the inclusive -1..+1 sigma value "
                 "region"),
                (dry.VALUE_AREA_POLICY, f"a later complete bar trades at or through {_w(d, '-', '+')}1 sigma"),
                (dry.REJECTION_POLICY, "that bar closes strictly back inside the boundary"),
                (dry.CONFIRMATION_POLICY, close + _w(d, "above the test bar high", "below the test bar low")))
    if family is dry.SetupFamily.RETURN_TO_VALUE:  # DOWN returns from above value, UP from below
        return ((dry.ACCEPTANCE_POLICY, "two consecutive complete 5m closes strictly beyond the same 1 sigma boundary"),
                (dry.RETURN_POLICY, "after that outside episode, a complete bar closes back inside the inclusive -1..+1 "
                 "sigma region"),
                (dry.ACCEPTANCE_POLICY, "two consecutive complete 5m closes inside value (the return close and the "
                 "next)"))
    slope, side = _w(d, "RISING", "FALLING"), _w(d, "ABOVE", "BELOW")
    return ((dry.VALUE_AREA_POLICY, f"an earlier complete close strictly {_w(d, 'above +', 'below -')}1 sigma"),
            (dry.RETURN_POLICY, "then a complete close back inside value (at or before the test)"),
            (dry.TREND_POLICY, f"at the bar before the test: Globex VWAP {slope} vs the previous bar and the close "
             f"strictly {side} the VWAP"),
            (dry.VWAP_TEST_POLICY, "a complete bar trades at or through the Globex VWAP"),
            (dry.CONFIRMATION_POLICY, close + _w(d, "above the test bar high", "below the test bar low")))


# What UP / DOWN means for each family (from the frozen docstrings; a reading, not a rule).
MEANING = {
    (dry.SetupFamily.PRICE_DISCOVERY_CONTINUATION, _UP): "an outside episode above +1 sigma: breakout, acceptance "
    "outside, a retest of +1 sigma, then upward confirmation",
    (dry.SetupFamily.PRICE_DISCOVERY_CONTINUATION, _DOWN): "an outside episode below -1 sigma: breakout, acceptance "
    "outside, a retest of -1 sigma, then downward confirmation",
    (dry.SetupFamily.FADE_VALUE_AREA_EXTREME, _UP): "price accepted inside value tests -1 sigma, closes back inside, "
    "then confirms upward toward the interior",
    (dry.SetupFamily.FADE_VALUE_AREA_EXTREME, _DOWN): "price accepted inside value tests +1 sigma, closes back inside, "
    "then confirms downward toward the interior",
    (dry.SetupFamily.RETURN_TO_VALUE, _UP): "after acceptance below -1 sigma, price closes back inside value and is "
    "accepted there (rotation up into value)",
    (dry.SetupFamily.RETURN_TO_VALUE, _DOWN): "after acceptance above +1 sigma, price closes back inside value and is "
    "accepted there (rotation down into value)",
    (dry.SetupFamily.VWAP_BOUNCE, _UP): "after a close above +1 sigma and a return inside value, a pullback tests the "
    "rising Globex VWAP from above, then confirms upward",
    (dry.SetupFamily.VWAP_BOUNCE, _DOWN): "after a close below -1 sigma and a return inside value, a pullback tests "
    "the falling Globex VWAP from below, then confirms downward",
}


def catalog() -> dict:
    """The catalog document (canonical JSON-safe; strings only)."""
    fams = {}
    for f in FAMILIES:
        fams[f.value] = {
            "title": TITLES[f], "short": SHORT[f], "candidate_policy": dry.CANDIDATE_POLICY[f],
            "source_criteria": list(dry.SOURCE_CRITERIA[f]),
            "directions": {d.value: {"meaning": MEANING[(f, d)],
                                     "conditions": [{"order": i + 1, "policy_id": p, "rule": r}
                                                    for i, (p, r) in enumerate(_conditions(f, d))]}
                           for d in DIRECTIONS}}
    return {"version": CATALOG_VERSION, "candidates_policy": dry.CANDIDATES_POLICY, "families": fams,
            "states": [s.value for s in dry.CandidateState], "condition_statuses": [s.value for s in dry.ConditionStatus],
            "stages": [s.value for s in dry.Stage]}


CATALOG = catalog()
CATALOG_SHA256 = hashlib.sha256(canonical_json(CATALOG).encode("ascii")).hexdigest()


def policy_of(family: str, direction: str, order: int) -> str:
    return CATALOG["families"][family]["directions"][direction]["conditions"][order - 1]["policy_id"]


def catalog_text() -> str:
    """The catalog as compact prompt text (deterministic; part of the versioned system prompt)."""
    lines = []
    for f, fam in CATALOG["families"].items():
        lines.append(f"{f} ({fam['title']}; {fam['candidate_policy']}). Source says: " + "; ".join(fam["source_criteria"])
                     + ".")
        for d, v in fam["directions"].items():
            conds = "; ".join(f"{c['order']} {c['policy_id']}: {c['rule']}" for c in v["conditions"])
            lines.append(f"  {f} {d}: {v['meaning']}. Laboratory V1 conditions: {conds}.")
    return "\n".join(lines)
