// 0AC-A4 guided Drysdale lesson in the browser: mode state, request bodies, the lesson bar, setup evidence (no network).
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TutorView } from "./TutorPane";
import {
  INITIAL_TUTOR,
  guidedAskAt,
  turnBody,
  tutorReducer,
  type Evidence,
  type LessonView,
  type TurnResponse,
  type TutorState,
} from "./tutor";

const D = "2026-09-30";
const START = "2026-09-30T13:30:00+00:00"; // 08:30 CT
const AT_0850 = "2026-09-30T13:50:00+00:00";
const AT_0900 = "2026-09-30T14:00:00+00:00";
const LESSON: LessonView = {
  lesson_id: "DRYSDALE_GUIDED_L1", version: "TUTOR_POC_GUIDED_LESSON_V1", trading_date: D,
  title: "Guided lesson 1 · the first half hour of the cash session", start_cutoff_utc: START,
  locked_semantics: { vwap_anchor: "GLOBEX" },
};

function guided(): TutorState {
  return tutorReducer(INITIAL_TUTOR, { type: "mode", mode: "guided", lesson: LESSON });
}

function reply(s: TutorState, at: string, lesson: LessonView, stage: TurnResponse["stage"] = "QUESTION"): TutorState {
  const asked = tutorReducer(s, { type: "request", action: "question", trading_date: D, replay_cutoff_utc: at });
  return tutorReducer(asked, { type: "reply", response: { turn_id: `t${s.nextTurn}`, turn: s.nextTurn, role: "tutor",
    action: "question", text: "What changed?", stage, trading_date: D, replay_cutoff_utc: at, provider: "fake",
    status: "FAKE", mode: "guided", lesson } });
}

function view(state: TutorState, extra: Partial<Parameters<typeof TutorView>[0]> = {}) {
  const noop = () => {};
  return renderToStaticMarkup(
    <TutorView state={state} cutoff={AT_0850} draft="" evidenceOpen={false} evidence={null} evidenceError={null}
      onDraft={noop} onSend={noop} onAction={noop} onToggleEvidence={noop} {...extra} />,
  );
}

describe("guided lesson state", () => {
  it("switches mode, resets the stage and carries the lesson id only in guided requests", () => {
    const s = guided();
    expect([s.mode, s.lesson?.lesson_id, s.stage]).toEqual(["guided", "DRYSDALE_GUIDED_L1", "QUESTION"]);
    expect(turnBody(s, "hint", AT_0850, "page-1")).toEqual({ action: "hint", replay_cutoff_utc: AT_0850, stage: "QUESTION",
      turn: 0, session_id: "page-1", mode: "guided", lesson_id: "DRYSDALE_GUIDED_L1" });
    const free = tutorReducer(s, { type: "mode", mode: "free", lesson: null });
    expect(turnBody(free, "message", AT_0850, "page-1", "hi")).toEqual({ action: "message", replay_cutoff_utc: AT_0850,
      stage: "QUESTION", turn: 0, session_id: "page-1", mode: "free", text: "hi" });
    expect(free.lesson).toBeNull();
  });

  it("never switches mode under a pending turn", () => {
    const pending = tutorReducer(INITIAL_TUTOR, { type: "request", action: "question", trading_date: D, replay_cutoff_utc: START });
    expect(tutorReducer(pending, { type: "mode", mode: "guided", lesson: LESSON })).toBe(pending);
  });

  it("follows the server's phase and reveal for the active lesson", () => {
    let s = reply(guided(), AT_0850, { ...LESSON, phase: "DEVELOPMENT", phase_label: "Development", revealed: false });
    expect(s.lesson?.phase).toBe("DEVELOPMENT");
    expect(s.lesson?.setup).toBeUndefined();
    const revealed = { ...LESSON, title: "VWAP_BOUNCE UP (VWAP Bounce) · BOUNCE-UP-20260930T1350Z", phase: "POST_REVEAL",
      revealed: true, setup: { family: "VWAP_BOUNCE", direction: "UP", instance_id: "BOUNCE-UP-20260930T1350Z" } };
    s = reply(s, AT_0900, revealed, "POST_REVEAL");
    expect([s.stage, s.lesson?.revealed, s.lesson?.setup?.family]).toEqual(["POST_REVEAL", true, "VWAP_BOUNCE"]);
  });

  it("asks once per replay position, and the lesson start only once the chart is there", () => {
    const s = guided();
    expect(guidedAskAt(s, AT_0850, null, START)).toBe(false); // still moving to the lesson start
    expect(guidedAskAt(s, START, null, START)).toBe(true);
    expect(guidedAskAt(s, START, START, null)).toBe(false); // already asked here
    expect(guidedAskAt(s, AT_0850, START, null)).toBe(true); // the Human advanced the replay
    expect(guidedAskAt(INITIAL_TUTOR, AT_0850, null, null)).toBe(false); // free chat: the Human asks
    const pending = tutorReducer(s, { type: "request", action: "hint", trading_date: D, replay_cutoff_utc: START });
    expect(guidedAskAt(pending, AT_0850, START, null)).toBe(false);
  });
});

describe("guided lesson view", () => {
  it("offers Start Guided Lesson in free chat only when a lesson exists", () => {
    expect(view(INITIAL_TUTOR, { lessons: [LESSON], onStartLesson: () => {} })).toContain(">Start Guided Lesson</button>");
    expect(view(INITIAL_TUTOR, { lessons: [] })).not.toContain("Start Guided Lesson");
    expect(view(guided(), { lessons: [LESSON], onStartLesson: () => {} })).not.toContain("Start Guided Lesson");
  });

  it("shows the mode, the neutral title, the phase and the Globex lock while a lesson is active", () => {
    const s = reply(guided(), AT_0850, { ...LESSON, phase: "DEVELOPMENT", phase_label: "Development: what changed" });
    const html = view(s, { onEndLesson: () => {} });
    expect(html).toContain("Guided Lesson");
    expect(html).toContain(LESSON.title);
    expect(html).toContain("Development: what changed");
    expect(html).toContain("VWAP anchor GLOBEX (locked by lesson)");
    expect(html).toContain(">End lesson</button>");
    expect(html).toContain("guided lesson");
    expect(html).not.toContain("VWAP_BOUNCE"); // the setup is not named before the reveal
  });

  it("Show Evidence lists each recent bar with its own bands and the frozen setup states", () => {
    const ev: Evidence = {
      schema: "TUTOR_POC_EVIDENCE_V1", trading_date: D, replay_cutoff_utc: AT_0850, provenance: {},
      latest_bar: { start_utc: 1790776800, end_utc: 1790777100 }, items: [{ key: "close", label: "Close", value: 7759 }],
      recent_bars: [{ start_utc: 1790776500, end_utc: 1790776800, close: 7754.25, vwap: 7748.1, upper_1sd: 7757.33,
        lower_1sd: 7738.87, upper_2sd: 7766.55, lower_2sd: 7729.65 }],
      setups: [{ family: "VWAP_BOUNCE", direction: "UP", instance_id: "BOUNCE-UP-20260930T1350Z", state: "DEVELOPING",
        stage: "WAITING_FOR_CONFIRMATION", conditions: [{ order: 1, policy_id: "DRYSDALE_VALUE_AREA_V1", status: "SATISFIED" },
          { order: 5, policy_id: "LAB_DIRECTIONAL_CONFIRMATION_V1", status: "PENDING" }] }],
      setup_analysis: { state: "QUALITY_QUALIFIED", quality_status: "QUALITY_QUALIFIED" },
    };
    const html = view(INITIAL_TUTOR, { evidenceOpen: true, evidence: ev });
    expect(html).toContain("7757.33");
    expect(html).toContain("7766.55");
    expect(html).toContain("VWAP_BOUNCE UP");
    expect(html).toContain("WAITING_FOR_CONFIRMATION");
    expect(html).toContain("✓ …");
  });
});
