import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import { ChartAttribution, CompanyLogo, LIGHTWEIGHT_CHARTS_NOTICE } from "./Branding";
import { CHART_LAYOUT } from "./Chart";

describe("branding and attribution (A2P2)", () => {
  it("company logo is an image with alt text", () => {
    const html = renderToStaticMarkup(<CompanyLogo />);
    expect(html).toMatch(/<img class="company-logo" src="[^"]*company_logo[^"]*\.png" alt="M8 logo"\/>/);
  });

  it("attribution carries the NOTICE text and a link to tradingview.com", () => {
    const html = renderToStaticMarkup(<ChartAttribution />);
    expect(LIGHTWEIGHT_CHARTS_NOTICE.product).toBe("TradingView Lightweight Charts™");
    expect(LIGHTWEIGHT_CHARTS_NOTICE.copyright).toBe("Copyright (с) 2025 TradingView, Inc."); // as published
    expect(html).toContain("TradingView Lightweight Charts™");
    expect(html).toContain("Copyright (с) 2025 TradingView, Inc.");
    expect(html).toContain('<a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">');
  });

  it("the chart's built-in TradingView logo is turned off", () => {
    expect(CHART_LAYOUT.attributionLogo).toBe(false);
    expect(CHART_LAYOUT.background).toEqual({ color: "#131722" }); // accepted chart look unchanged
  });

  it("the app shell shows the logo in the header and the attribution in the footer", () => {
    const html = renderToStaticMarkup(<App />);
    const header = html.slice(html.indexOf('<header class="topbar">'), html.indexOf("</header>"));
    const footer = html.slice(html.indexOf('<footer class="statusbar">'), html.indexOf("</footer>"));
    expect(header).toContain('class="company-logo"');
    expect(header).toContain("Dick&#x27;s Laboratory · Tutor POC");
    expect(footer).toContain('href="https://www.tradingview.com/"');
    expect(html).toContain('class="chart-pane"');
    expect(html).toContain('class="pane-divider"');
    expect(html).toContain('class="tutor-pane"');
    // the chart pane holds no TradingView branding of ours
    const chart = html.slice(html.indexOf('class="chart-pane"'), html.indexOf('class="pane-divider"'));
    expect(chart.toLowerCase()).not.toContain("tradingview");
  });
});
