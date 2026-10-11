"""0AA-A real-data proof for one dataset (scratch harness; outputs evidence)."""
import resource, sys
import time as clock
from pathlib import Path
from dicks_laboratory import market_study_state as mss
from dicks_laboratory.replay_player import ReplaySession
from dicks_laboratory.tutor_evidence import (LessonStage, QuestionKind, build_tutor_lesson, canonical_json,
    example_lesson, instructor_view, render_view, rubric_ref_coverage, student_view, validate_answer_grounding)

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
case, db, prior, commit = sys.argv[2], Path(sys.argv[3]), (Path(sys.argv[4]) if sys.argv[4] != "-" else None), sys.argv[5]
log = open(out / f"{case}.log", "w")
FORBIDDEN = ("bullish", "bearish", "buy", "sell", "setup", "entry", "target", "probability", "confidence",
             "recommend", "signal", "initiative", "responsive")
def say(*a):
    print(*a, file=log, flush=True); print(*a, flush=True)
def rss(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
t0 = clock.monotonic()
session = ReplaySession.load(db, mss.AnalysisProvenance(commit, False), prior)
say(f"[{case}] prepare session (replay layer): {clock.monotonic()-t0:.1f}s rss {rss():.0f} MB")
for spec in sys.argv[6:]:
    name, kind, at, frm, rv = spec.split("|")
    frm, rv = frm or None, rv or None
    t1 = clock.monotonic()
    lesson = build_tutor_lesson(session, example_lesson(session, QuestionKind(kind), at, frm, rv))
    first = clock.monotonic() - t1  # includes computing any snapshot not yet cached (replay layer)
    t2 = clock.monotonic()
    again = build_tutor_lesson(session, example_lesson(session, QuestionKind(kind), at, frm, rv))
    views = [student_view(again, s) for s in LessonStage] + [instructor_view(again)]
    texts = [canonical_json(v) for v in views]
    incremental = clock.monotonic() - t2  # snapshots cached: tutor layer (+ the delta newly-known scan if comparing)
    same = [canonical_json(v) for v in [student_view(lesson, s) for s in LessonStage] + [instructor_view(lesson)]] == texts
    report = validate_answer_grounding(lesson.answer_key.reference_answer, lesson)
    cited, missing = rubric_ref_coverage(lesson.answer_key.reference_answer, lesson)
    q = student_view(lesson)
    qtext = canonical_json(q)
    leak = []
    if lesson.future_outcome is not None:
        fsha = lesson.future_outcome.evidence.snapshot_sha256
        leak = [s.value for s in LessonStage if fsha in canonical_json(student_view(lesson, s))]
    hidden_ok = all(k not in q for k in ("answer_key", "hints", "future_outcome"))
    rendered = render_view(q) + render_view(instructor_view(lesson))
    bad_words = [w for w in FORBIDDEN if w in rendered.lower()]
    (out / f"{case}_{name}_student_QUESTION.txt").write_text(render_view(q))
    (out / f"{case}_{name}_instructor.txt").write_text(render_view(instructor_view(lesson)))
    (out / f"{case}_{name}_student_QUESTION.json").write_text(qtext + "\n")
    (out / f"{case}_{name}_instructor.json").write_text(texts[-1] + "\n")
    say(f"[{case}] {name}: {lesson.definition.lesson_id}")
    say(f"    support {lesson.answer_key.support.value} summary {lesson.answer_key.summary!r}; items "
        f"{len(lesson.context.items())}; warnings {[w.warning_id for w in lesson.context.quality_warnings]}")
    say(f"    snapshot {lesson.context.snapshot_sha256}; student payload {q['payload_sha256']}; instructor "
        f"{views[-1]['payload_sha256']}; definition {lesson.definition_sha256}")
    say(f"    reference answer grounded {report.valid} ({report.checked_refs} refs); rubric refs cited "
        f"{len(cited)}/{len(cited) + len(missing)}; QUESTION payload hides answer/hints/future {hidden_ok}; "
        f"future sha in student stages {leak}; deterministic {same}; forbidden words {bad_words}")
    say(f"    build {first:.2f}s (first, incl. snapshots); tutor layer with cached snapshots {incremental:.3f}s "
        f"(rebuild + 5 payloads); student payload {len(qtext):,} bytes")
say(f"[{case}] peak rss {rss():.0f} MB")
