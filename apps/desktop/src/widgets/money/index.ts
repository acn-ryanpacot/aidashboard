import { defineWidget } from '@jarvis/widget-sdk';

import { MoneyWidget } from './MoneyWidget';

/**
 * Debts and bills from your own spreadsheets in the documents folder: what's
 * due in the next two weeks and what you owe. Jarvis also speaks a reminder a
 * few days before each payment. The core reads the sheets at `/api/money`;
 * see `docs/guides/money.md`.
 */
export default defineWidget({
  manifest: {
    id: 'money',
    name: 'Money',
    description: 'Bills and debt payments coming due, and what you owe, from your spreadsheets.',
    version: '1.0.0',
    defaultSize: { cols: 2, rows: 3 },
    minRows: 2,
    source: { kind: 'builtin' },
    permissions: ['storage', 'voice-intents', 'notifications'],
    voiceIntents: ['money.bills', 'money.debts'],
  },
  component: MoneyWidget,
});
