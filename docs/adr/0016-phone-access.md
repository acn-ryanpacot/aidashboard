# 0016. Phone access through `tailscale serve` with device tokens

- Status: Accepted
- Date: 2026-11-11

## Context

The user wants Jarvis on their phone, away from home, at no cost. Constraints:

- Phone browsers allow the microphone only on HTTPS pages (or localhost), so plain `http://<tailscale-ip>:8765` would allow typing but never voice.
- The desktop app expects the core on `http://127.0.0.1:8765`; that must not change.
- Nothing should be reachable from the LAN or the internet, and tokens must not end up in URLs or logs.

## Decision

1. **Network.** `tailscale serve --bg 8765` publishes the core at `https://<pc>.<tailnet>.ts.net`, with a real certificate, only to the user's tailnet, proxying to `127.0.0.1:8765`. The core keeps binding to loopback only.
2. **Trust.** A request is *local* (trusted, as before) only if it comes from a loopback address **and** carries no proxy headers (`X-Forwarded-For`, `Forwarded`, `X-Forwarded-Host`, `Tailscale-User-Login`). That's necessary because `serve` connects from loopback too. Everything else needs a device token.
3. **Device tokens.**
   - Pairing creates `secrets.token_urlsafe(32)`. Only its SHA-256 is stored (migration 5, `device_tokens`), and it's shown once, as a QR code of `https://<pc>/#pair=<token>`. A fragment never reaches a server or a log.
   - The browser keeps the token in `localStorage` and sends `Authorization: Bearer` on HTTP.
   - On the voice WebSocket, which can't carry headers from a browser, it offers the subprotocols `jarvis.v3, bearer.<token>`, so no `?token=` query string ever shows up in access logs.
   - An unpaired WebSocket is accepted and then closed with code **4401**, so the UI can show the pairing screen instead of retrying.
4. **Least privilege.** `/api/devices` (pair, list, revoke, Tailscale status) is local-only: a paired phone can use Jarvis but can't mint or revoke tokens.
5. **Same UI.** The core serves the built dashboard at `/` (static files mounted after the API, public since they hold no data). The UI derives the core's address from its own origin when served this way. The WebSocket Origin check also accepts the page's own origin.

## Alternatives considered

- **Bind the core to `0.0.0.0` or the Tailscale IP.** No HTTPS (no phone microphone), it's exposed on the LAN, and the desktop app's loopback address would break or need a second listener.
- **Trust Tailscale's identity headers instead of tokens.** Simpler, but any device or shared node in the tailnet would get in, with no per-device revocation.
- **TLS in uvicorn with `tailscale cert`.** Certificates need renewing, and the desktop app would need HTTPS on loopback too.

## Consequences

- **+** Zero cost, nothing exposed beyond the tailnet, real HTTPS, and per-device revocation.
- **+** The same React app serves the desktop and the phone (responsive layout, installable as a home-screen app).
- **−** The dashboard must be built (`pnpm --filter @jarvis/desktop build`) for the core to serve it, and rebuilt after updates.
- **−** Web pages on phones pause when the screen locks, so the wake word only works while Jarvis is open.
- **−** The PC must be on; Jarvis isn't a cloud service.
