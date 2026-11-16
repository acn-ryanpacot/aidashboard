# Money: bills and debts

The **Money** widget shows what's due in the next two weeks and what you owe, and Jarvis reminds you before each payment. It reads **your own spreadsheets** in your documents folder. Jarvis never connects to a bank, and nothing leaves your PC.

## Setup

1. Set up your documents folder ([Knowledge sources → Your documents](web-search.md#your-documents)).
2. Put a **debts** sheet and/or a **bills** sheet in it, in Excel (`.xlsx`) or CSV, laid out as below.
3. Add the widget: click the layout icon (or **Ctrl+K → Edit layout**) → **Add widget** → **Money**.

Changes to the sheets show up within five minutes, or straight away with **Re-index now** in Settings → Knowledge. The ↻ button on the widget refreshes it.

## Laying out the sheets

Jarvis recognises the sheets by their column headers. The order of the columns doesn't matter, and a title row above the headers is fine.

**Debts**: any sheet with a balance column.

| Creditor | Balance | Monthly payment | Rate | Due day |
| --- | --- | --- | --- | --- |
| BDO card | ₱52,000 | ₱5,000 | 3.5% | 18 |
| Pag-IBIG loan | ₱122,000 | ₱3,100 | 6.25% | 5th |

- **Balance**: also `Owed`, `Outstanding`, `Remaining`, `Principal`, `Utang`.
- **Monthly payment**: also `Monthly`, `Payment`, `Amortization`, `Installment`, `Minimum`, `Hulog`.
- **Rate** and **Due day** are optional. With a due day, each monthly payment also appears under *Due soon* and gets a reminder.

**Bills**: a sheet with a due column and an amount.

| Bill | Amount | Due date |
| --- | --- | --- |
| Meralco | ₱3,210.50 | 2026-11-20 |
| PLDT | ₱1,699 | 25 |
| Netflix | 549 | every 2nd |

**Due dates** can be written as:

- a **date**: `2026-11-20`, `11/20/2026` (month first unless the day is over 12), `Nov 20`, `20 November 2026`;
- a **day of the month**, meaning it repeats monthly: `25`, `25th`, `every 2nd`, `30 of every month`. The 31st means the last day of shorter months.

**Overdue or recurring?**

- Without a **Paid** column, a date that has passed rolls forward a month, on the assumption that the bill repeats. Last month's Meralco date becomes this month's.
- With a **Paid** (or **Status**) column, an unpaid date that has passed is shown as **overdue**, in red, and rows marked `yes`, `paid`, `done`, `x` or `✓` are skipped.

Other details:

- A row labelled **Total** is ignored, so your own totals row isn't counted twice.
- Amounts may include `₱`, `PHP`, `$` and thousands separators. Rates may be `3.5%` or `0.035`.
- A sheet that has none of these columns (a grocery list, say) is simply ignored.

## The widget

- **Due soon**: the total due in the next 14 days, then each payment with its date. Gold means it's within your reminder window; red means overdue.
- **Debts**: the total owed, your monthly payments, and each debt with its rate and a bar comparing it with the largest.
- **Eye button**: hides every amount (`•••••`), for screen sharing or when someone's looking. The choice is remembered on that device.

## Reminders

Jarvis says, for example, *"Ryan, your Meralco bill of ₱3,210.50 is due in 3 days, on Friday."*, and again on the day itself (*"…is due today."*). Overdue items are mentioned once.

- Choose how early in **Settings → Knowledge → Bill reminders**: off, the day before, or 2, 3, 5 or 7 days before. The default is 3.
- Reminders are spoken only between **8 AM and 9 PM**, and wait for an open Jarvis window. They're also kept in the notifications bell.
- The **morning briefing** mentions payments due this week.

## Asking Jarvis

- *"What bills are due this week?"*
- *"How much do I owe in total?"*
- *"When is my Meralco bill due?"*
- *"What's my biggest debt?"*
- *"How much is left on the BDO card?"*

The `get_bills_and_debts` tool answers the first four. For totals and filtered rows from any spreadsheet, Jarvis uses `read_spreadsheet`.

## Privacy

Everything is read locally from your files. Paired phones can see the widget and ask about it too. Revoke a lost phone in **Settings → Phone access**. Use the eye button if you show your dashboard to others.
