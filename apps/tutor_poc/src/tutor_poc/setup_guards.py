"""Setup-aware answer guards for the Drysdale Tutor (0AC-A4): TUTOR_POC_SETUP_GUARDS_V1.

They run after the frozen validator and the frozen Drysdale answer guards (dicks_laboratory.tutor_ai), on what
the model wrote in prose. Each check compares a statement with the deterministic evidence of the same turn; none
adds or changes a setup rule.

    SETUP_STATE_CONTRADICTED     a setup called valid / complete / a candidate whose DRYSDALE state is not
                                 CANDIDATE or QUALITY_QUALIFIED
    CONDITION_NOT_GROUNDED       "acceptance has occurred" (retest, rejection, confirmation, breakout, return to
                                 value, VWAP test, trend context) without citing a SATISFIED condition of that policy
    BAND_RELATION_CONTRADICTED   "the prior bar closed above +2 sigma" when that bar's own relation says otherwise
    FUTURE_STATED_AS_KNOWN       "the next bar will break out", "a reversal is coming" (conditional pathways pass)
    ARITHMETIC_QUIZ              a question asking the student to compute a distance the evidence already gives
    HINT_GIVES_ANSWER            a hint that lays out more than one number for the student to compare
    EXPLAIN_NOT_LINKED           an explanation without fact -> interpretation -> setup relevance
    ENTRY_BEFORE_VALIDITY        entry talk without citing a setup whose state is CANDIDATE or QUALITY_QUALIFIED
    RISK_MANAGEMENT              account size, contracts, stops, risk amounts ... (out of Tutor scope)

Plus one narrow waiver of the frozen vocabulary rule: "bullish" / "bearish" are allowed as teaching judgment, i.e.
inside an AI_INTERPRETATION claim that cites evidence (and in answer_text / uncertainties when such a claim exists).
Every other frozen vocabulary word stays refused.

Sentences that are questions, negated or conditional ("not valid yet", "if a later bar ...", "would need") do not
assert anything and are not checked; this keeps the checks to positive assertions, the kind that can be false.
"""
from __future__ import annotations

import re
from enum import StrEnum

from dicks_laboratory.tutor_ai import DRYSDALE_VOCABULARY, GuardCode
from dicks_laboratory.tutor_evidence import EVIDENCE_CATEGORIES, ClaimCategory, GroundingIssue, TutorAnswer

from tutor_poc.evidence import ChartLesson, bar_rows
from tutor_poc.setups import DONE

GUARDS_VERSION = "TUTOR_POC_SETUP_GUARDS_V1"


class SetupGuardCode(StrEnum):
    SETUP_STATE_CONTRADICTED = "SETUP_STATE_CONTRADICTED"
    CONDITION_NOT_GROUNDED = "CONDITION_NOT_GROUNDED"
    BAND_RELATION_CONTRADICTED = "BAND_RELATION_CONTRADICTED"
    FUTURE_STATED_AS_KNOWN = "FUTURE_STATED_AS_KNOWN"
    ARITHMETIC_QUIZ = "ARITHMETIC_QUIZ"
    HINT_GIVES_ANSWER = "HINT_GIVES_ANSWER"
    EXPLAIN_NOT_LINKED = "EXPLAIN_NOT_LINKED"
    ENTRY_BEFORE_VALIDITY = "ENTRY_BEFORE_VALIDITY"
    RISK_MANAGEMENT = "RISK_MANAGEMENT"


_I = re.IGNORECASE
FAMILY = {
    "PRICE_DISCOVERY_CONTINUATION": re.compile(r"price[\s_-]+discovery[\s_-]+continuation|\bPDC\b", _I),
    "FADE_VALUE_AREA_EXTREME": re.compile(r"fade[\s_-]+value[\s_-]+area[\s_-]+extremes?|\bfade\b", _I),
    "RETURN_TO_VALUE": re.compile(r"return[\s_-]+to[\s_-]+value(?![\s_-]+(condition|close|bar))|\bRTV\b", _I),
    "VWAP_BOUNCE": re.compile(r"vwap[\s_-]+bounce", _I),
}
_DIR_AFTER = re.compile(r"^[\s(_-]{0,3}(up|down)\b", _I)
_DIR_WORD = {"UP": re.compile(r"\b(upward|bullish)\b", _I), "DOWN": re.compile(r"\b(downward|bearish)\b", _I)}
VALID = re.compile(r"\b(is|are|was|has become|became|now|been)\b[^.?!;]{0,40}?\b(valid|complete[d]?|a (laboratory v1 )?"
                   r"candidate|quality[_ -]qualified|conditions_satisfied|(all )?(its |the )?(five |four |three )?"
                   r"conditions (are |were |have been )?(now )?(all )?satisfied)\b", _I)
SKIP = re.compile(r"n't\b|\b(not|no|none|nothing|never|neither|nor|yet to|until|unless|if|would|could|might|may|needs?|needed|"
                  r"before|whether|without|incomplete|missing|pending|developing|once|when|still)\b", _I)
HEDGE = re.compile(r"\b(i'?d read|i would (read|describe|call)|i read (this|it)|looks? like|appears?|seems?|suggests?|"
                   r"in my reading|arguably|could be read|my interpretation|interpret)\b", _I)
CONCEPTS = (
    ("LAB_ACCEPTANCE_TIME_V1", re.compile(r"acceptance|accepted\s+(above|below|outside|inside|into|back)", _I)),
    ("LAB_RETEST_V1", re.compile(r"\b(re-?test(ed)?|back-?test(ed)?)\b", _I)),
    ("LAB_REJECTION_V1", re.compile(r"\b(rejection|rejected)\b", _I)),
    ("LAB_DIRECTIONAL_CONFIRMATION_V1", re.compile(r"\b(confirmation|confirmed|first sign of (strength|weakness))\b", _I)),
    ("LAB_BREAKOUT_TRIGGER_V1", re.compile(r"\b(breakout|broke out|break[- ]out)\b", _I)),
    ("LAB_RETURN_TO_VALUE_V1", re.compile(r"\b(return(ed)? to value|returned inside|back inside value)\b", _I)),
    ("LAB_VWAP_TEST_V1", re.compile(r"\b(vwap test|tested the vwap|test of the vwap)\b", _I)),
    ("LAB_TREND_CONTEXT_V1", re.compile(r"\btrend context\b", _I)),
)
OCCURRED = re.compile(
    r"\b(has|have|had)\s+(now\s+|already\s+)?(occurred|happened|formed|been\s+(established|satisfied|observed|confirmed|"
    r"met|completed))\b|\b(is|was|are|were)\s+(now\s+|already\s+)?(established|satisfied|present|in place|met|observed|"
    r"confirmed|complete[d]?)\b|\b(we have|there is|there was|we got|shows?|showed|showing|gave|gives)\s+(an?\s+|the\s+)?"
    r"(acceptance|re-?test|back-?test|rejection|confirmation|breakout|vwap test)\b|\b(price|the market|it|the bar)\s+"
    r"(has\s+)?(accepted|retested|rejected|broke out|confirmed)\b|\boccurred\b", _I)
BAND = re.compile(r"\bclos(?:e|es|ed|ing)\b[^.?!;]{0,40}?\b(above|over|below|under|beyond|outside)\s+(?:the\s+)?"
                  r"([+\-−]?)\s?([12])\s?(?:σ|sigma|sd|standard deviations?)", _I)
TIME = re.compile(r"(?<![\d.])(\d{1,2}):(\d{2})(?!\d)")
LATEST = re.compile(r"\b(latest|last|current|this|most recent|new)\s+(completed\s+)?(bar|candle|close)\b|"
                    r"\b(close is|closes|close sits|close stays)\b", _I)
PRIOR = re.compile(r"\b(prior|previous|preceding)\s+(bar|candle|close)\b", _I)
FUTURE = re.compile(
    r"\b(price|the market|it|the next (?:5-minute |5m )?(?:bar|candle)|the next few (?:bars|candles)|this (?:bar|setup|"
    r"move|trend)|the setup|buyers|sellers|vwap|the (?:bullish|bearish|upward|downward) (?:move|trend|reversal|"
    r"breakout))\s+(will|is going to|are going to|is about to|is bound to|won't|will not)\b|\b(is|are) coming\b|"
    r"\bwe know (that )?(this|it|price)\b|\bnext (bar|candle) (will|should)\b|\bwill (break out|reverse|bounce|rally|"
    r"drop|fall|rise|continue)\b", _I)
CONDITIONAL = re.compile(r"\b(if|unless|should (price|it|a later|the next)|in case|whether|only when|once|until|when|"
                         r"would)\b", _I)
ARITHMETIC = re.compile(
    r"\b(calculate|compute|subtract|work out|add up)\b|\bwhat(?:'s| is)\s+\d[\d.,]*\s*[-−+x×]\s*\d|\bhow (many|much|"
    r"far)\b[^?]{0,40}\b(points?|ticks?|distance)\b|\bexact(ly)?\b[^?]{0,30}\b(distance|points?|gap|difference)\b|"
    r"\bwhat(?:'s| is) the (exact )?(distance|difference|gap)\b|\bby how (much|many)\b", _I)
DECIMAL = re.compile(r"(?<![\w.])\d[\d,]*\.\d+")
ENTRY = re.compile(r"\b(entr(y|ies)|enter)\b", _I)
RISK = re.compile(
    r"\b(account (size|balance)|risk (per trade|percent(age)?|budget|amount)|\d+(\.\d+)?\s?%\s+(of (your|the) account|"
    r"risk)|position[- ]siz(e|ing)|number of contracts|how many contracts|\d+\s+contracts?|lot size|daily loss|"
    r"max(imum)? (daily )?loss|capital allocation|portfolio|exposure|stop[- ]loss|stop (placement|level|order)|place "
    r"(a |your )?stop|dollar risk|risk[- ]reward|reward[- ]to[- ]risk|profit target|take[- ]profit)\b", _I)
BIAS = re.compile(r"\b(bullish|bearish)\b", _I)
RESIDUAL_VOCABULARY = re.compile(DRYSDALE_VOCABULARY.pattern.replace("bullish|bearish|", ""), _I)
assert RESIDUAL_VOCABULARY.pattern != DRYSDALE_VOCABULARY.pattern  # the frozen word list still starts this way


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _texts(a: TutorAnswer) -> list[tuple[str, str, ClaimCategory | None]]:
    out = [("answer_text", a.answer_text, None)]
    out += [(f"claims[{i}]", c.statement, c.category) for i, c in enumerate(a.claims)]
    out += [(f"uncertainties[{i}]", u, None) for i, u in enumerate(a.uncertainties)]
    return out


def _asserts(s: str) -> bool:
    return not s.endswith("?") and not SKIP.search(s)


class _View:
    """The deterministic facts the checks read, from the turn's own two documents."""

    def __init__(self, cl: ChartLesson) -> None:
        sdoc = cl.setup_document
        self.setup_sha, self.items = cl.setup_sha256, {i.ref: i for i in cl.lesson.context.items()}
        self.valid = {(r["family"], r["direction"]) for r in sdoc["setups"] if r["state"] in DONE}
        self.valid |= {(r["family"], r["direction"]) for r in sdoc["completed_today"] if r["state"] in DONE}
        self.condition_policy = {f"/setups/{i}/conditions/{j}/status": c["policy_id"]
                                 for i, r in enumerate(sdoc["setups"]) for j, c in enumerate(r["conditions"])}
        self.rows = [r for _, r in bar_rows(cl.document)]

    def valid_state(self, family: str, direction: str | None) -> bool:
        return any(f == family and (direction is None or d == direction) for f, d in self.valid)


def _direction(s: str, m: re.Match) -> str | None:
    after = _DIR_AFTER.match(s[m.end():])
    if after:
        return after[1].upper()
    found = [d for d, rx in _DIR_WORD.items() if rx.search(s)]
    return found[0] if len(found) == 1 else None


def _state_issues(where: str, text: str, v: _View) -> list[GroundingIssue]:
    out = []
    for s in _sentences(text):
        if not VALID.search(s) or not _asserts(s):
            continue
        for family, rx in FAMILY.items():
            for m in rx.finditer(s):
                d = _direction(s, m)
                if not v.valid_state(family, d):
                    out.append(GroundingIssue(SetupGuardCode.SETUP_STATE_CONTRADICTED, where, None,
                                              f"{family}{' ' + d if d else ''} is stated as valid / complete but no "
                                              "such instance is CANDIDATE or QUALITY_QUALIFIED at this cutoff"))
    return out


def _cited_satisfied(a: TutorAnswer, v: _View) -> set[str]:
    """Policies whose SATISFIED status (or acceptance / trend context fact) some claim cites."""
    out = set()
    for c in a.claims:
        for r in c.evidence_refs:
            if r.source_sha256 != v.setup_sha or r not in v.items:
                continue
            val = v.items[r].value
            if r.pointer in v.condition_policy and val == "SATISFIED":
                out.add(v.condition_policy[r.pointer])
            elif r.pointer == "/context/current_episode_lab_acceptance_time_v1" and val is True:
                out.add("LAB_ACCEPTANCE_TIME_V1")
            elif r.pointer == "/context/trend_context" and val in ("UP", "DOWN"):
                out.add("LAB_TREND_CONTEXT_V1")
    return out


def _condition_issues(where: str, text: str, supported: set[str]) -> list[GroundingIssue]:
    out = []
    for s in _sentences(text):
        if not OCCURRED.search(s) or not _asserts(s) or HEDGE.search(s):
            continue
        for policy, rx in CONCEPTS:
            if rx.search(s) and policy not in supported:
                out.append(GroundingIssue(SetupGuardCode.CONDITION_NOT_GROUNDED, where, None,
                                          f"{rx.search(s)[0]!r} stated as having happened without citing a SATISFIED "
                                          f"{policy} condition from DRYSDALE"))
    return out


def _band_issues(where: str, text: str, v: _View) -> list[GroundingIssue]:
    out = []
    if not v.rows:
        return out
    for s in _sentences(text):
        if not _asserts(s):
            continue
        start = 0
        for m in BAND.finditer(s):
            clause, start = s[start:m.end()], m.end()  # the bar a relation is about is named before it
            word, sign, k = m[1].lower(), m[2], m[3]
            if word in ("beyond", "outside") and not sign:
                continue
            upper = sign == "+" or (not sign and word in ("above", "over"))
            want = "ABOVE" if word in ("above", "over") or (word in ("beyond", "outside") and upper) else "BELOW"
            col = f"close_vs_{'upper' if upper else 'lower'}_{k}sd"
            times = {f"{int(h):02d}:{mm}" for h, mm in TIME.findall(clause)}
            rows = [r for r in v.rows if r["start_ct"] in times or r["end_ct"] in times]
            if times and not rows:
                continue  # a bar outside the window: the bars cannot check it (the setup conditions may)
            if not rows:
                if PRIOR.search(clause) and len(v.rows) > 1:
                    rows = [v.rows[-2]]
                elif LATEST.search(clause):
                    rows = [v.rows[-1]]
                else:
                    rows = v.rows
            if not any(r[col] == want for r in rows):
                out.append(GroundingIssue(SetupGuardCode.BAND_RELATION_CONTRADICTED, where, None,
                                          f"{m[0]!r}: the cited bar's {col} is "
                                          f"{', '.join(sorted({r[col] for r in rows}))}"))
    return out


def _future_issues(where: str, text: str) -> list[GroundingIssue]:
    return [GroundingIssue(SetupGuardCode.FUTURE_STATED_AS_KNOWN, where, None,
                           f"{FUTURE.search(s)[0]!r}: a later outcome stated as known; describe it as a conditional "
                           "pathway (if ... then ...)")
            for s in _sentences(text) if FUTURE.search(s) and not s.endswith("?") and not CONDITIONAL.search(s)]


def _bias_waiver(issues: tuple[GroundingIssue, ...], a: TutorAnswer) -> tuple[GroundingIssue, ...]:
    """Drop the frozen vocabulary issue for bullish / bearish used as cited AI interpretation; re-check the rest."""
    interp = any(c.category is ClaimCategory.AI_INTERPRETATION and c.evidence_refs and BIAS.search(c.statement)
                 for c in a.claims)
    texts = {w: (t, cat) for w, t, cat in _texts(a)}
    out = []
    for i in issues:
        if i.code is GuardCode.LABORATORY_VOCABULARY and i.where in texts and BIAS.search(i.detail or ""):
            text, cat = texts[i.where]
            if i.where.startswith("claims"):
                ok = cat is ClaimCategory.AI_INTERPRETATION and a.claims[int(i.where[7:-1])].evidence_refs
            else:
                ok = interp
            if ok:
                m = RESIDUAL_VOCABULARY.search(text)
                if m:
                    out.append(GroundingIssue(GuardCode.LABORATORY_VOCABULARY, i.where, None,
                                              f"{m[0]!r} is not used in Laboratory evidence answers"))
                continue
        out.append(i)
    return tuple(out)


def setup_guards(answer: TutorAnswer, cl: ChartLesson, action: str | None = None) -> tuple[GroundingIssue, ...]:
    v = _View(cl)
    supported = _cited_satisfied(answer, v)
    issues: list[GroundingIssue] = []
    for where, text, cat in _texts(answer):
        issues += _state_issues(where, text, v)
        issues += _condition_issues(where, text, supported)
        issues += _band_issues(where, text, v)
        issues += _future_issues(where, text)
        for s in _sentences(text):
            if s.endswith("?") and ARITHMETIC.search(s):
                issues.append(GroundingIssue(SetupGuardCode.ARITHMETIC_QUIZ, where, None,
                                             f"{ARITHMETIC.search(s)[0]!r}: ask what the given distance means, not "
                                             "for the arithmetic"))
        m = RISK.search(text)
        if m:
            issues.append(GroundingIssue(SetupGuardCode.RISK_MANAGEMENT, where, None,
                                         f"{m[0]!r}: risk management and execution are outside Tutor scope"))
        if ENTRY.search(text) and not _cites_valid_state(answer, v):
            issues.append(GroundingIssue(SetupGuardCode.ENTRY_BEFORE_VALIDITY, where, None,
                                         "entry discussed without citing a setup whose state is CANDIDATE or "
                                         "QUALITY_QUALIFIED"))
    if action == "hint" and len(set(DECIMAL.findall(answer.answer_text))) > 1:
        issues.append(GroundingIssue(SetupGuardCode.HINT_GIVES_ANSWER, "answer_text", None,
                                     "a hint names where to look; it does not lay out the numbers to compare"))
    if action == "explain":
        fact = any(c.category in EVIDENCE_CATEGORIES for c in answer.claims)
        interp = any(c.category is ClaimCategory.AI_INTERPRETATION for c in answer.claims)
        setup = any(r.source_sha256 == v.setup_sha for c in answer.claims for r in c.evidence_refs) or any(
            rx.search(t) for _, t, _ in _texts(answer) for rx in FAMILY.values())
        if not (fact and interp and setup):
            issues.append(GroundingIssue(SetupGuardCode.EXPLAIN_NOT_LINKED, "claims", None,
                                         "an explanation links a cited fact, an AI_INTERPRETATION and its setup "
                                         "relevance (cite a DRYSDALE item or name a setup)"))
    return tuple(issues)


def _cites_valid_state(a: TutorAnswer, v: _View) -> bool:
    for c in a.claims:
        for r in c.evidence_refs:
            item = v.items.get(r)
            if item is not None and r.source_sha256 == v.setup_sha and r.pointer.endswith("/state") \
                    and item.value in DONE:
                return True
    return False


def apply(frozen: tuple[GroundingIssue, ...], answer: TutorAnswer, cl: ChartLesson,
          action: str | None = None) -> tuple[GroundingIssue, ...]:
    """Frozen guard issues after the bullish / bearish waiver, plus the setup guards."""
    return _bias_waiver(frozen, answer) + setup_guards(answer, cl, action)
