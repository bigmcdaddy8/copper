import { DEFAULT_SETTINGS, OVERLAY_GROUPS, setOverlay, type ChartSettings, type LineStyleName } from "./settings";

interface Props {
  settings: ChartSettings;
  onChange: (s: ChartSettings) => void;
}

export function SettingsPanel({ settings, onChange }: Props) {
  const { presentation, study } = settings;
  return (
    <div className="settings">
      <h3>Presentation</h3>
      <p className="hint">Changes how the chart looks. Never changes market values.</p>
      {OVERLAY_GROUPS.map(({ group, label }) => {
        const o = presentation.overlays[group];
        return (
          <div className="setting-row" key={group}>
            <label>
              <input
                type="checkbox"
                checked={o.visible}
                onChange={(e) => onChange(setOverlay(settings, group, { visible: e.target.checked }))}
              />
              {label}
            </label>
            <input
              type="color"
              value={o.color}
              aria-label={`${label} color`}
              onChange={(e) => onChange(setOverlay(settings, group, { color: e.target.value }))}
            />
            <select
              value={o.lineStyle}
              aria-label={`${label} line style`}
              onChange={(e) => onChange(setOverlay(settings, group, { lineStyle: e.target.value as LineStyleName }))}
            >
              <option value="solid">solid</option>
              <option value="dashed">dashed</option>
              <option value="dotted">dotted</option>
            </select>
          </div>
        );
      })}
      <div className="setting-row">
        <span>Candles</span>
        <input
          type="color"
          value={presentation.candles.up}
          aria-label="up candle color"
          onChange={(e) =>
            onChange({ ...settings, presentation: { ...presentation, candles: { ...presentation.candles, up: e.target.value } } })
          }
        />
        <input
          type="color"
          value={presentation.candles.down}
          aria-label="down candle color"
          onChange={(e) =>
            onChange({ ...settings, presentation: { ...presentation, candles: { ...presentation.candles, down: e.target.value } } })
          }
        />
      </div>
      <button className="link" onClick={() => onChange({ ...settings, presentation: DEFAULT_SETTINGS.presentation })}>
        Reset presentation
      </button>

      <h3>Study</h3>
      <p className="hint">Changes what the Laboratory computes (server-side).</p>
      <div className="setting-row">
        <span>VWAP anchor</span>
        <select value={study.vwap_anchor} disabled={study.locked} aria-label="VWAP anchor">
          <option value="GLOBEX">Globex session open (17:00 CT)</option>
        </select>
        {study.locked && <span className="lock">🔒 locked</span>}
      </div>
    </div>
  );
}
