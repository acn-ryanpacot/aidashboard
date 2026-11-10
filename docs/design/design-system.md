# Design system

The goal is the restraint of a high-end instrument panel. The screen is dark, quiet and precise, and the colour and light are reserved for the assistant itself.

## Principles

1. **One hero.** The core is the only saturated, glowing element. Everything else is glass and grey.
2. **Light means life.** Glow intensity encodes activity: idle breathes, speaking pulses.
3. **Calm motion.** One easing curve everywhere, `cubic-bezier(0.22, 1, 0.36, 1)` (ease-out-quint). Entrances are 0.3–0.7 s; nothing bounces.
4. **Typography over chrome.** Hierarchy comes from size, weight and letter-spacing, not boxes and dividers.
5. **Respect the user.** Honour `prefers-reduced-motion`, make everything keyboard-reachable, and keep contrast at least 4.5:1 for body text.

## Tokens (`apps/desktop/src/styles/global.css`)

| Token                 | Value       | Use                                   |
| --------------------- | ----------- | ------------------------------------- |
| `void`                | `#04060b`   | App background                        |
| `ink`                 | `#0a0f1a`   | Raised surfaces                       |
| `arc-400`             | `#5ee7ff`   | Primary accent, live indicators       |
| `arc-200` / `arc-300` | `#b5f5ff` / `#8cecff` | Highlighted text, active words |
| `gold-400`            | `#ffc45c`   | "Thinking", warnings                  |
| `signal-red`          | `#ff5c7a`   | Errors only                           |

Orb state colours live in `orbRenderer.ts` (`STATE_COLOURS`).

## Type

- **Inter Variable** for UI and prose (stylistic sets `cv11`, `ss01`, `ss03` enabled).
- **JetBrains Mono Variable** for labels, numbers and status, set in uppercase with 0.2–0.4 em tracking.
- Fonts are bundled through Fontsource, so they work offline with no CDN.

| Role            | Style                                                       |
| --------------- | ----------------------------------------------------------- |
| Wordmark        | 13 px, semibold, tracking 0.55 em                           |
| Panel label     | Mono 10 px, uppercase, tracking 0.28 em, 45 % white         |
| Clock           | 56 px, extralight, tabular numbers                          |
| Caption         | 24 px, light, tight tracking, balanced wrapping             |
| Body            | 13.5 px, relaxed leading                                    |

## Surfaces

`glass`: a 1.25 rem radius, a 1 px border at 7 % white, a top-lit vertical gradient, an inset highlight, a long soft shadow, and `backdrop-filter: blur(20px) saturate(140%)`. `glass-pill` is its compact sibling for status chips and icon buttons.

The background stacks three faint radial glows, a 56 px HUD grid masked to the centre, and a vignette.

## Components

| Component       | File                                   |
| --------------- | -------------------------------------- |
| Panel           | `components/ui/GlassPanel.tsx`         |
| Status dot      | `components/ui/StatusDot.tsx`          |
| Core / orb      | `components/hud/Orb.tsx` + `orbRenderer.ts` |
| Captions        | `components/hud/Captions.tsx`          |
| Command bar     | `components/hud/CommandBar.tsx`        |

When adding UI, reuse these before inventing new surfaces. Add new tokens to `@theme` rather than hard-coding colours.
