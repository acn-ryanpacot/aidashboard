# Standalone widget packages

Built-in widgets live in `apps/desktop/src/widgets/`. This folder is for widgets that are developed as their own workspace package, for example one maintained alongside a mobile app.

Each package should:

- be named `@jarvis/widget-<name>`;
- depend on `@jarvis/widget-sdk` and have `react` as a peer dependency;
- default-export a `defineWidget(...)` definition;
- be added to `apps/desktop/package.json` and registered in `apps/desktop/src/dashboard/registry.ts`.

See [docs/guides/adding-a-widget.md](../docs/guides/adding-a-widget.md).
