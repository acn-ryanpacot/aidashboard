# 0015. Companion apps plug in through a core-side adapter

- Status: Accepted
- Date: 2026-11-11

## Context

Jarvis is meant to show widgets from the user's own apps. The first one, **PisoTiyempo** (a PSE investing app), already publishes the user's data on the same PC:

- a read-only JSON API on `127.0.0.1` while its desktop app runs;
- `summary.json` and CSV files in its export folder after every sync.

The dashboard could call that API directly from the browser, but that would need CORS changes in the other app, would make the widget unusable when that app is closed, and would leave the voice layer and the briefing without the data.

## Decision

1. **The core service owns the integration.** A `PortfolioSource` port gets a `PisoTiyempoPortfolio` adapter. It reads the live feed and falls back to the export files. It only reads the real-money account.
2. An application service (`PortfolioService`) adds what Jarvis needs: the session label ("today" vs "last session", in Philippine time), peso moves per holding, and the trend-and-value **ideas screen**. Widgets, voice tools (`get_portfolio`, `get_stock_ideas`) and the briefing all use that one service.
3. The widget is declared with `source: { kind: 'mobile-app', appId, endpoint }` and reads only the core's proxy route, `/api/apps/pisotiyempo`. Future companion apps follow the same pattern: one adapter, one service, one `/api/apps/<app>` route.
4. The integration is **read-only**. Jarvis never writes to the other app's data.
5. **Alerts** (added later) aren't in the feed, so a second adapter, `PisoTiyempoAlerts`, reads the alert rules and latest quotes from PisoTiyempo's SQLite file. The app's README offers that file for dashboards, and Jarvis opens it in read-only mode (`?mode=ro`). Jarvis applies the phone app's conditions itself and keeps its own "announced once per trading day" record in its own preferences table.

The screen is rules-based and shows its reasons, rather than asking the language model to pick stocks: a local model has no market data and would invent picks. PisoTiyempo has no fundamentals, so "value" means *a reasonable entry within an uptrend* (RSI and the 50-day average), not P/E.

## Consequences

- **+** Works whether the other app is open (live feed) or closed (export files), and the same data reaches the widget, the voice answers and the briefing.
- **+** No changes needed in PisoTiyempo apart from one config line (see below), and no CORS.
- **−** PisoTiyempo's feed defaults to port 8765, which is Jarvis's port. The user must set `feedPort=8766` in its config. `jarvis-doctor` detects the clash, and both the guide and the Settings screen explain it.
- **−** Data is end of day (PisoTiyempo syncs daily), so the widget isn't a live ticker.
