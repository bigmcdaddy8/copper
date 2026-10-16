// Chart | Tutor divider. The accepted A2 width is the Tutor minimum; the chart keeps CHART_MIN_PX.

export const TUTOR_MIN_PX = 240;
export const TUTOR_MIN_FRACTION = 0.26;
export const TUTOR_DEFAULT_MAX_PX = 400;
export const CHART_MIN_PX = 480;
export const WIDTH_STORAGE_KEY = "tutor_poc.tutorWidthPx";

/** The accepted A2 Tutor width, clamp(240px, 26%, 400px): the minimum normal width. */
export function minTutorWidth(containerPx: number): number {
  return Math.min(Math.max(TUTOR_MIN_PX, TUTOR_MIN_FRACTION * containerPx), TUTOR_DEFAULT_MAX_PX);
}

/** The Tutor width actually used for a requested width (null = default). Minimum wins on tiny screens. */
export function clampTutorWidth(requestedPx: number | null, containerPx: number): number {
  const min = minTutorWidth(containerPx);
  if (requestedPx === null) return min;
  const max = containerPx - CHART_MIN_PX;
  return Math.max(min, Math.min(requestedPx, max));
}

/** Width requested by a pointer at clientX; the Tutor pane ends at the container's right edge. */
export function tutorWidthAtPointer(clientX: number, containerRight: number): number {
  return Math.round(containerRight - clientX);
}

/** CSS flex-basis for a requested width that re-applies the same limits when the window is resized. */
export function tutorFlexBasis(requestedPx: number): string {
  const min = `clamp(${TUTOR_MIN_PX}px, ${TUTOR_MIN_FRACTION * 100}%, ${TUTOR_DEFAULT_MAX_PX}px)`;
  return `clamp(${min}, ${requestedPx}px, calc(100% - ${CHART_MIN_PX}px))`;
}

export function loadTutorWidth(): number | null {
  try {
    const v = Number(window.localStorage.getItem(WIDTH_STORAGE_KEY));
    return Number.isFinite(v) && v > 0 ? v : null;
  } catch {
    return null;
  }
}

export function saveTutorWidth(px: number | null): void {
  try {
    if (px === null) window.localStorage.removeItem(WIDTH_STORAGE_KEY);
    else window.localStorage.setItem(WIDTH_STORAGE_KEY, String(px));
  } catch {
    // storage unavailable: the width just isn't remembered
  }
}
