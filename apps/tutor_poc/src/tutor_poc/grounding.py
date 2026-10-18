"""Grounding validation for a real-model Tutor answer (0AC-A3).

    model JSON -> parse_answer (frozen, strict)                    INVALID_STRUCTURED_OUTPUT on any shape error
               -> validate_answer_grounding (frozen, authoritative) refs exist, are authorized, values / categories match
               -> answer_guards (frozen V2)                         trade advice, bias vocabulary, undefined policies
               -> text_guards (POC, below)                          numbers / times written in prose
               -> setup_guards (POC, A4)                            setup state, conditions, band relations,
                                                                    future-as-known, arithmetic quiz, hint /
                                                                    explain shape, entry timing, risk scope

0AC-A4: the lesson is in the frozen Drysdale module, so answer_guards applies the frozen Drysdale (two-voice)
guards; setup_guards.apply narrowly waives their bullish / bearish refusal for cited AI interpretation.

The frozen validator checks the values a claim *asserts*. A model can still write a number or a time in the
prose (answer_text, a claim statement, an uncertainty) without asserting it, e.g. "The current VWAP is
9999.00". text_guards closes that gap for this POC: every decimal number, every number with three or more
digits, every clock time and every ISO date written there must be a value of an authorized evidence item
(a rounded form of one is accepted). Small integers ("2 sigma", "5-minute", "6 bars") are not checked.
Unsupported claims are not checked: they exist to name what the evidence does not contain.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum

from dicks_laboratory.tutor_ai import InvalidStructuredOutput, TutorRunStatus, answer_guards, parse_answer
from dicks_laboratory.tutor_evidence import (
    GroundingIssue,
    GroundingReport,
    LessonStage,
    TutorAnswer,
    validate_answer_grounding,
)

from tutor_poc import setup_guards
from tutor_poc.evidence import ChartLesson


class TextGuardCode(StrEnum):
    UNGROUNDED_NUMBER = "UNGROUNDED_NUMBER"
    UNGROUNDED_TIME = "UNGROUNDED_TIME"
    UNGROUNDED_DATE = "UNGROUNDED_DATE"


_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_TIME = re.compile(r"(?<![\d.])(\d{1,2}):(\d{2})(?![\d])")
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def _decimal(v) -> Decimal | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return Decimal(str(v).replace(",", ""))
    except InvalidOperation:
        return None


def _allowed(cl: ChartLesson, student_text: str | None) -> tuple[set[Decimal], set[str], set[str]]:
    values = [i.value for i in cl.lesson.context.items()]
    numbers = {abs(d) for v in values if (d := _decimal(v)) is not None}
    times = {v for v in values if isinstance(v, str) and re.fullmatch(r"\d{2}:\d{2}", v)}
    dates = {cl.document["trading_date"]}
    if student_text:  # the student's own numbers may be echoed back; they are not Laboratory facts
        numbers |= {d for t in _NUMBER.findall(_TIME.sub(" ", student_text)) if (d := _decimal(t)) is not None}
        times |= {f"{int(h):02d}:{m}" for h, m in _TIME.findall(student_text)}
    return numbers, times, dates


def _matches(token: Decimal, allowed: set[Decimal]) -> bool:
    exp = token.as_tuple().exponent
    for v in allowed:
        if token == v:
            return True
        if isinstance(exp, int) and v.as_tuple().exponent < exp:  # a rounded form of an authorized value
            q = Decimal(1).scaleb(exp)
            if token in (v.quantize(q, rounding=ROUND_HALF_EVEN), v.quantize(q, rounding=ROUND_HALF_UP)):
                return True
    return False


def text_guards(answer: TutorAnswer, cl: ChartLesson, student_text: str | None = None) -> tuple[GroundingIssue, ...]:
    numbers, times, dates = _allowed(cl, student_text)
    texts = [("answer_text", answer.answer_text)] + [(f"claims[{i}]", c.statement) for i, c in enumerate(answer.claims)]
    texts += [(f"uncertainties[{i}]", u) for i, u in enumerate(answer.uncertainties)]
    issues = []
    for where, text in texts:
        for d in _DATE.findall(text):
            if d not in dates:
                issues.append(GroundingIssue(TextGuardCode.UNGROUNDED_DATE, where, None, f"date {d} is not in the evidence"))
        rest = _DATE.sub(" ", text)
        for h, m in _TIME.findall(rest):
            if f"{int(h):02d}:{m}" not in times:
                issues.append(GroundingIssue(TextGuardCode.UNGROUNDED_TIME, where, None,
                                             f"time {h}:{m} is not a time in the evidence"))
        for tok in _NUMBER.findall(_TIME.sub(" ", rest)):
            d = _decimal(tok)
            if d is None or ("." not in tok and len(tok.replace(",", "")) < 3):
                continue
            if not _matches(d, numbers):
                issues.append(GroundingIssue(TextGuardCode.UNGROUNDED_NUMBER, where, None,
                                             f"{tok} is not a value in the evidence"))
    return tuple(issues)


def evaluate(text: str, cl: ChartLesson, stage: LessonStage, student_text: str | None = None, action: str | None = None
             ) -> tuple[TutorRunStatus, TutorAnswer | None, GroundingReport | None, tuple[GroundingIssue, ...], str | None]:
    """(status, answer, report, issues, detail) -- the frozen tutor_ai._evaluate plus text and setup guards."""
    try:
        answer = parse_answer(text, cl.lesson, stage)
    except InvalidStructuredOutput as exc:
        return TutorRunStatus.INVALID_STRUCTURED_OUTPUT, None, None, (), str(exc)
    report = validate_answer_grounding(answer, cl.lesson)
    issues = (report.issues + setup_guards.apply(answer_guards(answer, cl.lesson), answer, cl, action)
              + text_guards(answer, cl, student_text))
    return (TutorRunStatus.GROUNDED if not issues else TutorRunStatus.GROUNDING_FAILED), answer, report, issues, None


def grounding_summary(answer: TutorAnswer, report: GroundingReport, cl: ChartLesson) -> dict:
    """What the browser may show about an accepted answer: each claim's category and the evidence it cites."""
    items = {i.ref: i for i in cl.lesson.context.items()}

    def cite(r):
        it = items.get(r)
        return {"pointer": r.pointer, "label": it.label if it else r.pointer, "value": it.value if it else None}

    setups, missing = [], []
    for c in answer.claims:
        for r in c.evidence_refs:
            if r.source_sha256 != cl.setup_sha256 or not r.pointer.startswith("/setups/"):
                continue
            row = cl.setup_document["setups"][int(r.pointer.split("/")[2])]
            tag = f"{row['family']} {row['direction']}"
            if tag not in setups:
                setups.append(tag)
            it = items.get(r)
            if "/conditions/" in r.pointer and r.pointer.endswith("/status") and it and it.value in (
                    "PENDING", "NOT_SATISFIED"):
                cond = row["conditions"][int(r.pointer.split("/")[4])]
                entry = f"{tag} {cond['policy_id']} {it.value}"
                if entry not in missing:
                    missing.append(entry)
    return {"checked_refs": report.checked_refs, "interpretations": report.interpretations,
            "referenced_setups": setups, "missing_conditions": missing,
            "claims": [{"category": c.category.value, "statement": c.statement,
                        "cites": [cite(r) for r in c.evidence_refs]} for c in answer.claims],
            "unsupported": [{"support": u.support.value, "statement": u.statement, "missing": list(u.missing)}
                            for u in answer.unsupported_claims]}
