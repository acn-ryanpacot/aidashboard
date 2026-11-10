# App icons

Generated, not hand-made. From `apps/desktop`, run:

```bash
pnpm tauri icon app-icon.svg
```

This writes every size Tauri needs (`32x32.png`, `128x128.png`, `icon.ico`, `icon.icns`, …)
into this folder. If your Tauri CLI version rejects SVG input, export `app-icon.svg` to a
1024×1024 PNG first and pass that instead.
