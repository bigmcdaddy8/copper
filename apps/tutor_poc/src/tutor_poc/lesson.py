"""Guided Drysdale lessons (0AC-A4): TUTOR_POC_GUIDED_LESSON_V1.

A guided lesson is a replay window on an already-inspected development date, a few checkpoints that set the
teaching phase, and one setup instance the lesson studies. The instance is taken from the frozen Laboratory
analysis (0AB-B audit, docs/dicks_laboratory/evidence/0AB-B), never authored here, and `verify` checks it against
the prepared setup timeline before the lesson can be used.

No-lookahead: what the model is told before `reveal_at` is outcome-neutral (the phase instructions never name the
studied setup, its outcome or a later bar) and the title is neutral. From `reveal_at` the lesson block also names
the studied instance; by then the evidence at the cutoff already contains its completed state. The evidence itself
is always the current cutoff's, in guided mode and in free chat alike.

Lesson semantics lock: Drysdale lessons use the source-aligned Globex-anchored VWAP (AI_TUTOR_UX_POC_PLAN.md,
"Lesson-Semantic Locking"). The lock is part of the lesson and is shown while the lesson is active.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from tutor_poc.setups import DONE, SetupTimeline

LESSON_SCHEMA = "TUTOR_POC_GUIDED_LESSON_V1"
CT = ZoneInfo("America/Chicago")
HIERARCHY = ("OBSERVE", "COMPARE", "CHARACTERIZE_STRUCTURE", "NARROW_SETUPS", "IDENTIFY_MISSING_CONDITIONS",
             "EVALUATE_VALIDITY", "DISCUSS_POTENTIAL_ENTRY_LOCATION", "REVIEW")
PHASES = ("BEFORE_SETUP", "DEVELOPMENT", "DECISION", "POST_REVEAL")
LOCKED_SEMANTICS = {"vwap_anchor": "GLOBEX"}


@dataclass(frozen=True)
class Phase:
    phase: str  # one of PHASES
    at_ct: str  # HH:MM: the phase applies from this replay cutoff until the next phase
    label: str  # what the Human sees
    levels: tuple[str, ...]  # teaching hierarchy levels this phase works on
    instructions: str  # for the model; outcome-neutral before the reveal
    fake_text: str  # the scripted Tutor's question (fake provider)


@dataclass(frozen=True)
class GuidedLesson:
    lesson_id: str
    trading_date: date
    title: str  # neutral: shown before the reveal
    revealed_title: str  # shown from reveal_at
    phases: tuple[Phase, ...]  # ascending at_ct; the last one is POST_REVEAL
    family: str  # the studied instance (frozen DRYSDALE_SETUP_ANALYSIS_V1), named only from reveal_at
    direction: str
    instance_id: str
    progression: tuple[tuple[str, str], ...]  # (HH:MM, what the frozen analysis shows then): handoff / reveal only
    version: str = LESSON_SCHEMA
    locked: tuple[tuple[str, str], ...] = tuple(LOCKED_SEMANTICS.items())

    def at(self, hhmm: str) -> datetime:
        h, m = (int(x) for x in hhmm.split(":"))
        return datetime.combine(self.trading_date, time(h, m), tzinfo=CT)

    @property
    def start(self) -> datetime:
        return self.at(self.phases[0].at_ct)

    @property
    def reveal_at(self) -> datetime:
        return self.at(next(p.at_ct for p in self.phases if p.phase == "POST_REVEAL"))

    def phase_at(self, cutoff: datetime) -> Phase:
        current = self.phases[0]
        for p in self.phases:
            if self.at(p.at_ct) <= cutoff:
                current = p
        return current

    def revealed(self, cutoff: datetime) -> bool:
        return cutoff >= self.reveal_at

    def public(self, cutoff: datetime | None = None) -> dict:
        """What the browser may show (no instance, no outcome before the reveal)."""
        out = {"lesson_id": self.lesson_id, "version": self.version, "trading_date": self.trading_date.isoformat(),
               "title": self.title, "start_cutoff_utc": self.start.astimezone(UTC).isoformat(),
               "locked_semantics": dict(self.locked)}
        if cutoff is not None:
            p = self.phase_at(cutoff)
            out |= {"phase": p.phase, "phase_label": p.label, "revealed": self.revealed(cutoff),
                    "before_start": cutoff < self.start}
            if self.revealed(cutoff):
                out |= {"title": self.revealed_title, "setup": {"family": self.family, "direction": self.direction,
                                                                "instance_id": self.instance_id}}
        return out

    def block(self, cutoff: datetime) -> dict:
        """The lesson section of the model request at this cutoff."""
        p = self.phase_at(cutoff)
        out = {"lesson_id": self.lesson_id, "version": self.version, "title": self.title,
               "locked_semantics": dict(self.locked),
               "phase": {"phase": p.phase, "label": p.label, "levels": list(p.levels), "instructions": p.instructions,
                         "from_ct": p.at_ct, "at_phase_start": cutoff == self.at(p.at_ct)},
               "before_start": cutoff < self.start, "reveal": None}
        if out["before_start"]:
            out["phase"]["instructions"] = (f"The replay is before the lesson start ({self.phases[0].at_ct} CT). Ask "
                                            "the student to step the replay forward to the lesson start.")
        if self.revealed(cutoff):
            out["title"] = self.revealed_title
            out["reveal"] = {"studied_setup": {"family": self.family, "direction": self.direction,
                                               "instance_id": self.instance_id},
                             "progression": [{"at_ct": t, "laboratory": what} for t, what in self.progression],
                             "note": "Every fact here is also in the current DRYSDALE evidence; cite the evidence."}
        return out


def verify(lesson: GuidedLesson, st: SetupTimeline) -> list[str]:
    """Problems with the lesson against the prepared frozen analysis (empty: usable)."""
    problems = []
    if st.trading_date != lesson.trading_date:
        return [f"setup timeline is {st.trading_date}, lesson is {lesson.trading_date}"]
    if [p.phase for p in lesson.phases][-1] != "POST_REVEAL" or sorted(lesson.phases, key=lambda p: p.at_ct) != list(
            lesson.phases):
        problems.append("phases must ascend and end with POST_REVEAL")
    for p in lesson.phases:
        if st.at(lesson.at(p.at_ct)) is None:
            problems.append(f"{p.at_ct} is not a prepared replay position")
    at_reveal = st.at(lesson.reveal_at)
    if at_reveal is not None:
        done = [c for c in at_reveal["completed"] if c["candidate_id"] == lesson.instance_id]
        if not done or done[0]["state"] not in DONE or (done[0]["family"], done[0]["direction"]) != (
                lesson.family, lesson.direction):
            problems.append(f"{lesson.instance_id} is not a completed {lesson.family} {lesson.direction} at the reveal")
        target = next((c for c in at_reveal["latest"] if c["candidate_id"] == lesson.instance_id), None)
        for t, what in lesson.progression:
            if what.startswith("condition ") and target is not None:
                k = int(what.split()[1])
                got = target["conditions"][k - 1]["satisfied_at_utc"]
                if got is None or datetime.fromisoformat(got).astimezone(CT).strftime("%H:%M") != t:
                    problems.append(f"progression {t}: condition {k} of {lesson.instance_id} is satisfied at {got}")
    start = st.at(lesson.start)
    if start is not None and any(c["candidate_id"] == lesson.instance_id for c in start["completed"]):
        problems.append(f"{lesson.instance_id} is already complete at the lesson start")
    for p in lesson.phases:
        if p.phase != "POST_REVEAL":
            text = f"{lesson.lesson_id} {lesson.title} {p.label} {p.instructions} {p.fake_text}".lower()
            short = lesson.instance_id.split("-")[0].lower()  # PDC / FADE / RTV / BOUNCE
            for word in (lesson.instance_id.lower(), lesson.family.lower(), lesson.family.lower().replace("_", " "),
                         short):
                if word in text:
                    problems.append(f"phase {p.at_ct} names the studied setup before the reveal")
    return problems


# --- phases shared by the Drysdale lessons ---------------------------------------------------------------

def _phases(start: str, development: str, decision: str, review: str) -> tuple[Phase, ...]:
    return (
        Phase("BEFORE_SETUP", start, "Before the setup: location, structure, possibilities",
              ("OBSERVE", "COMPARE", "CHARACTERIZE_STRUCTURE", "NARROW_SETUPS"),
              "Start of a guided lesson; one step per turn, moving on as soon as the student has shown a step: "
              "(1) where the latest close sits relative to VWAP and the bands (accept an approximate answer); (2) how "
              "the last several bars read together as a sequence, using each bar's own band relations; (3) which of "
              "the eight directional setup possibilities the current structure makes implausible, and why; (4) which "
              "two or three remain worth watching and which conditions each still lacks. Do not repeat a step the "
              "student has already answered.",
              "Guided lesson. Start with location: where does the latest close sit relative to VWAP and the bands? "
              "Then look at the last few bars together: what story do they tell, and which setup possibilities "
              "does that rule out?"),
        Phase("DEVELOPMENT", development, "Development: what changed, what is present, what is missing",
              ("COMPARE", "NARROW_SETUPS", "IDENTIFY_MISSING_CONDITIONS"),
              "The replay advanced. Start from what the student concluded before (conversation) and ask what the "
              "newly completed bars changed, and what that does to the possibilities being watched: stronger, "
              "weaker or eliminated. Then ask which required Laboratory V1 conditions of the possibilities still in "
              "play are present and which are missing, using the DRYSDALE condition statuses. If a setup instance "
              "appeared or changed stage, ask what it still needs from a later bar (as a conditional pathway). Do "
              "not re-ask the candle location.",
              "The replay moved. Compared with what you concluded before, what did the new bar change? Which "
              "possibilities got stronger, weaker or disappeared, and what is each one still missing?"),
        Phase("DECISION", decision, "Decision point: is any setup valid yet?",
              ("EVALUATE_VALIDITY", "DISCUSS_POTENTIAL_ENTRY_LOCATION"),
              "Ask whether the deterministic Laboratory V1 conditions of any setup the student has been watching are "
              "now all satisfied, and to justify it from the evidence; correct or refine the reasoning against the "
              "DRYSDALE states. Only if a setup's state is CANDIDATE or QUALITY_QUALIFIED at this cutoff, discuss its "
              "potential entry location as a training concept: what evidence supports it and what would make the "
              "student hesitate (including its quality qualification). Otherwise discuss what is still missing.",
              "Decision point. Are all the Laboratory conditions of any setup you have been watching satisfied now? "
              "Explain which evidence says so, and what would make you hesitate."),
        Phase("POST_REVEAL", review, "Review (revealed)", ("REVIEW",),
              "The studied setup is now revealed (lesson.reveal). Review its progression from the evidence: which "
              "evidence mattered and when, which possibilities were eliminated earlier and why, what would have "
              "invalidated it (for example a confirmation bar that fails), and what the student noticed or missed. "
              "Then invite free questions about the other setup possibilities.",
              "Review. The lesson studied the setup shown in the header. Which evidence mattered most along the way, "
              "and what would have invalidated it?"),
    )


# 2026-09-30: VWAP_BOUNCE UP, BOUNCE-UP-20260930T1350Z (0AB-B audit: first 08:50, completed 08:55 CT).
L1 = GuidedLesson(
    "DRYSDALE_GUIDED_L1", date(2026, 9, 30), "Guided lesson 1 · the first half hour of the cash session",
    "VWAP_BOUNCE UP (VWAP Bounce) · BOUNCE-UP-20260930T1350Z", _phases("08:30", "08:35", "08:55", "09:00"),
    "VWAP_BOUNCE", "UP", "BOUNCE-UP-20260930T1350Z",
    (("08:10", "condition 1 DRYSDALE_VALUE_AREA_V1: a complete close strictly above +1 sigma (bar ending 08:10)"),
     ("08:15", "condition 2 LAB_RETURN_TO_VALUE_V1: a close back inside value (bar ending 08:15)"),
     ("08:20", "RETURN_TO_VALUE DOWN RTV-DOWN-20260930T1315Z completes (QUALITY_QUALIFIED)"),
     ("08:35", "FADE_VALUE_AREA_EXTREME DOWN: +1 sigma tested and closed back inside; waiting for confirmation"),
     ("08:40", "FADE_VALUE_AREA_EXTREME DOWN: confirmation not satisfied"),
     ("08:45", "condition 3 LAB_TREND_CONTEXT_V1: Globex VWAP rising, close above it (bar before the test)"),
     ("08:50", "condition 4 LAB_VWAP_TEST_V1: the bar ending 08:50 trades at or through the Globex VWAP; the "
               "instance appears, WAITING_FOR_CONFIRMATION"),
     ("08:55", "condition 5 LAB_DIRECTIONAL_CONFIRMATION_V1 satisfied: QUALITY_QUALIFIED, CONDITIONS_SATISFIED; "
               "PRICE_DISCOVERY_CONTINUATION UP triggers on the same bar"),
     ("09:00", "post-reveal review")))

LESSONS: dict[date, tuple[GuidedLesson, ...]] = {L1.trading_date: (L1,)}
