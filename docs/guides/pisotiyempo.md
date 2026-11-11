# PisoTiyempo: your PSE portfolio in Jarvis

The **Portfolio** widget shows your Philippine Stock Exchange (PSE) portfolio from the [PisoTiyempo](https://github.com/acn-ryanpacot/pisotiyempo) app. It covers your latest trading session and each holding. If you hold no stocks, it suggests **three trend-and-value ideas to research**.

You can also ask by voice: *"How are my stocks doing?"* or *"What PSE stocks look good?"*. If you hold stocks, the morning briefing mentions your portfolio in one sentence.

!!! warning "Not financial advice"
    The ideas come from a simple, transparent screen of PisoTiyempo's daily analysis. They're a starting point for your own research, not recommendations.

## How it works

```
PisoTiyempo desktop app ──► 127.0.0.1:8766/api/…   (live feed while the app runs)
                       └──► %APPDATA%\PisoTiyempo\export\   (files, rewritten after every sync)
                                   │
Jarvis core ── PisoTiyempo adapter ┘ ──► /api/apps/pisotiyempo ──► Portfolio widget
                                    └──► get_portfolio / get_stock_ideas tools, briefing
```

Jarvis reads the live feed first. If the desktop app is closed, it reads the export files instead, so the widget still shows the last sync. It only reads your **real** account, never practice trades, and it never changes anything in PisoTiyempo.

The data is **end of day**: PisoTiyempo syncs once a day after the market closes. The widget says **Today** when the prices are from today's session (Philippine time), otherwise **Last session** with the date, e.g. over a weekend.

## Setup (once)

Both apps must run on the **same PC**, because PisoTiyempo's feed only answers on `127.0.0.1`.

### 1. Move PisoTiyempo's feed off port 8765

PisoTiyempo's feed uses port **8765** by default, the same port as the Jarvis core, so only one of them can start. (Worse, the Jarvis desktop app would see *something* on 8765 and assume the core is already running.)

1. Close PisoTiyempo.
2. Open `%APPDATA%\PisoTiyempo\config.properties` in Notepad. Paste `%APPDATA%\PisoTiyempo` into the Explorer address bar to find the folder. If the file doesn't exist yet, start and close PisoTiyempo once, or create it.
3. Add this line and save:

   ```properties
   feedPort=8766
   ```

4. Start PisoTiyempo again. In **Settings → Dashboard feed** it should now show `http://127.0.0.1:8766`.

**Check** in PowerShell (it lists the feed's endpoints):

```powershell
Invoke-RestMethod http://127.0.0.1:8766/api
```

### 2. Let PisoTiyempo sync

Open PisoTiyempo and let it finish its daily sync (or link your phone so your trades come across). Jarvis shows whatever PisoTiyempo has.

### 3. Add the widget

In Jarvis, click the **layout icon** (or **Ctrl+K → Edit layout**), then **Add widget → Portfolio**. A height of 3 rows fits about eight holdings or three ideas.

`jarvis-doctor` has a **PisoTiyempo** line that tells you whether it found the live feed or the export files.

## What the widget shows

**If you hold stocks:**

- **Today · Tue, Nov 10** (or **Last session · …**), then the day's change in pesos and percent.
- Portfolio value and overall profit or loss since you bought.
- Each holding: last price, % change and peso change on the day, biggest movers first.

**If you hold none:** up to three ideas, each with its price, PisoTiyempo score and the reasons it passed.

### The trend-and-value screen

A stock is an idea only if **all** of these hold, using PisoTiyempo's daily analysis:

| Rule | Why |
| --- | --- |
| **Liquid** (PisoTiyempo's flag) | You can buy and sell it without moving the price |
| **Above its 200-day average** | Long-term uptrend |
| **Up over the last 3 months** | The trend is still working |
| **RSI-14 of 55 or below** | *Value*: not overbought, ideally a pullback |
| **Score +20 or more** | PisoTiyempo's own buy line (score from −100 to +100) |

Passing stocks are ranked by score, then by lower RSI, and the top three are shown. A reason such as *"Dipped below its 50-day average"* marks a pullback within the uptrend.

PisoTiyempo has no P/E or dividend-yield data (that would need a paid fundamentals feed), so "value" here is about **entry price within a trend**, not about the company's earnings. If PisoTiyempo gains fundamentals later, the screen can use them without changing the widget.

The thresholds live in `IdeaRules` (`services/core/src/jarvis_core/application/portfolio.py`).

## Settings

| Where | Setting | Default |
| --- | --- | --- |
| **Settings → Companion apps** (live) | PisoTiyempo feed | `http://127.0.0.1:8766` (empty = export files only) |
| `services/core/.env` | `JARVIS_PORTFOLIO_ENABLED` | `true` |
| `services/core/.env` | `JARVIS_PORTFOLIO_EXPORT_DIR` | PisoTiyempo's default, `%APPDATA%\PisoTiyempo\export` |

If you changed PisoTiyempo's `exportDir`, set `JARVIS_PORTFOLIO_EXPORT_DIR` to the same folder.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Widget: *"PisoTiyempo isn't running"* | Start PisoTiyempo and let it sync; check step 1 (port 8766) |
| `jarvis-doctor`: *"8765 used by PisoTiyempo's dashboard feed"* | Step 1: `feedPort=8766`, then restart PisoTiyempo |
| The Jarvis window says "Core offline" although nothing seems wrong | PisoTiyempo's feed is on 8765; see step 1 |
| Widget shows **Last session** on a trading day | PisoTiyempo hasn't synced today's close yet |
| "No stock passes the screen today" | Nothing meets all five rules; this is common after a broad rally or a sell-off |
| Holdings are missing | Only the real account is shown; check that the trades are in PisoTiyempo (phone sync or CSV import) |
