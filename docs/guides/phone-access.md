# Phone access (Tailscale)

Use Jarvis from your phone, at home or away: the dashboard, typed questions and voice. It costs nothing and opens nothing to the internet.

```
Phone (Tailscale app) ──encrypted tailnet──► your PC: tailscale serve (HTTPS)
                                                  └─► Jarvis core on 127.0.0.1:8765
                                                        ├─ /          the dashboard
                                                        ├─ /api/…     needs the phone's device token
                                                        └─ /ws/voice  needs the phone's device token
```

- **Tailscale** connects your devices in a private network (a "tailnet") that only you can join. The free Personal plan is plenty.
- **`tailscale serve`** gives Jarvis an HTTPS address like `https://jarvis-pc.tail1234.ts.net`. Phone browsers only allow the microphone on HTTPS pages, so this is what makes voice work.
- **Nothing changes for this PC.** The core still listens only on `127.0.0.1`. Nothing is opened on your Wi-Fi network, and there are no firewall rules to add.
- **Every phone gets its own device token**, paired by scanning a QR code. Anything arriving through Tailscale must present a token, so a device on your tailnet that you didn't pair still can't use Jarvis. You can revoke a phone at any time.

## Setup (once)

### 1. Install Tailscale on the PC and the phone

1. On the PC, install Tailscale and sign in:

   ```powershell
   winget install --id Tailscale.Tailscale -e
   ```

   Tailscale appears in the system tray. Click **Log in** and pick an account (Google, Microsoft, GitHub or Apple).

2. On the phone, install **Tailscale** from the App Store or Google Play. Sign in with the **same account** and switch it on.

### 2. Turn on HTTPS for your tailnet

Open the Tailscale admin console, <https://login.tailscale.com/admin/dns>, and:

- make sure **MagicDNS** is enabled;
- under **HTTPS Certificates**, click **Enable HTTPS**.

### 3. Build the dashboard for phones

The core serves the dashboard to phones from `apps\desktop\dist`. From the repository folder:

```powershell
pnpm --filter @jarvis/desktop build
```

Restart the core (`pnpm dev:core`, or the desktop app). Rebuild after you `git pull` an update.

### 4. Publish Jarvis to your phone

```powershell
tailscale serve --bg 8765
```

The first time, Tailscale may print a link asking you to allow Serve on your tailnet; open it and click **Enable**. `--bg` keeps the setting across reboots. Tailscale then prints the HTTPS address. Check it with:

```powershell
tailscale serve status
```

!!! danger "Use `serve`, never `funnel`"
    `tailscale funnel` publishes to the **whole internet**. Jarvis would still require a device token, but there's no reason to expose it. `serve` stays inside your tailnet.

### 5. Pair the phone

1. On the PC, open Jarvis → **Settings → Phone access**. All three steps should show a check mark. If one doesn't, it tells you what's missing.
2. Type a name (e.g. *Ryan's iPhone*) and click **Pair a phone**. A QR code appears.
3. Point the **phone's camera** at it and open the link. Jarvis opens on the phone, already paired.

The code is shown only once and works like a password. If the phone can't scan it, click **Copy pairing link** and send the link to yourself another way, or paste the token on the phone's pairing screen.

### 6. Put Jarvis on the home screen

- **iPhone (Safari):** Share → **Add to Home Screen**.
- **Android (Chrome):** ⋮ → **Add to Home screen** / **Install app**.

It then opens full screen like an app.

### 7. Talk to it

Tap **Engage** and allow the microphone. Then tap the orb to speak, or type in the box under it.

## Using Jarvis on the phone

- The layout is one scrolling column: the orb and command bar first, then your widgets. Edit the layout on the PC; the phone shows the same widgets.
- Speech is recognised and spoken by the PC (GPU), so the phone just records and plays audio.
- **Wake word:** "Hello Jarvis" works while Jarvis is open on the screen. Phones pause web pages when the screen locks or you switch apps, so tapping the orb is usually more practical.
- Reminders, timers and stock alerts are spoken on every open Jarvis window, including the phone.
- The PC must be on, with the core running and Tailscale connected.

## Managing devices

**Settings → Phone access** lists paired devices and when each was last used. **×** revokes one immediately: its next request is refused and it shows the pairing screen again.

From a terminal (e.g. over remote desktop) you can do the same:

```powershell
cd services\core
uv run jarvis-token list
uv run jarvis-token create "Tablet"
uv run jarvis-token revoke 2
```

To stop phone access entirely: `tailscale serve reset`.

## Security, in short

- Requests that come straight from this PC are trusted, as before.
- Requests relayed by `tailscale serve` (they carry forwarding headers) or from any other address must send a valid device token: `Authorization: Bearer …` for HTTP, and a `bearer.…` WebSocket subprotocol for voice, so tokens never appear in URLs or logs.
- Only a SHA-256 hash of each token is stored (`~/.jarvis-os/jarvis.db`).
- Paired devices can use Jarvis and change its settings, but **only the PC** can pair or revoke devices.
- Design notes: [ADR-0016](../adr/0016-phone-access.md).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| The phone can't open the address | Tailscale is switched on on the phone? Same account? `tailscale status` on the PC should list the phone |
| "This device isn't paired yet" | Pair again from **Settings → Phone access** (the device may have been revoked) |
| The page loads but says *Core offline* | Rebuild the dashboard after updates (step 3) and restart the core |
| The microphone doesn't work | Use the `https://…ts.net` address (not `http://100.x…`); allow the mic in the browser's site settings; on iPhone, try Safari if the home-screen app doesn't ask |
| `jarvis-doctor` warns *Jarvis isn't published* | Run `tailscale serve --bg 8765` again; `tailscale serve status` shows what's published |
| *Enable HTTPS* errors from `tailscale serve` | Step 2 (HTTPS certificates in the admin console) |
