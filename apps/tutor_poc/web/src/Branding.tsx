// Application branding and the third-party chart attribution (0AC-A2P2).
import logoUrl from "../../../../docs/company_logo.png";

// Verbatim from the NOTICE file of tradingview/lightweight-charts at tag v5.1.0 (the installed version).
// The npm package does not ship NOTICE; its README requires this notice plus a link to
// https://www.tradingview.com/ on a page available to users. The "с" in "(с)" is reproduced as published.
export const LIGHTWEIGHT_CHARTS_NOTICE = {
  product: "TradingView Lightweight Charts™",
  copyright: "Copyright (с) 2025 TradingView, Inc.",
  url: "https://www.tradingview.com/",
} as const;

export function CompanyLogo() {
  return <img className="company-logo" src={logoUrl} alt="M8 logo" />;
}

export function ChartAttribution() {
  const n = LIGHTWEIGHT_CHARTS_NOTICE;
  return (
    <span className="attribution">
      Charts: {n.product} · {n.copyright}{" "}
      <a href={n.url} target="_blank" rel="noopener noreferrer">
        {n.url}
      </a>
    </span>
  );
}
