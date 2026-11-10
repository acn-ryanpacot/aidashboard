# Voice ID: answer only Ryan

With voice ID on, Jarvis compares every request to your *voiceprint* and ignores anyone else, including the TV.

## Enable

```bash
cd services/core
uv sync --group dev --extra voice --extra speaker
```

In `services/core/.env`:

```dotenv
JARVIS_SPEAKER_VERIFICATION=true
JARVIS_SPEAKER_THRESHOLD=0.30
JARVIS_SPEAKER_ENROLLMENT_SAMPLES=3
```

The first start downloads SpeechBrain's ECAPA-TDNN model (~80 MB) into `~/.jarvis-os/models/ecapa`.

## Enroll

1. Open the dashboard and click **Enroll** on the **Systems** widget.
2. Read each prompt aloud in your normal voice, at your usual distance from the mic. Each one takes a few seconds.
3. After three samples you'll see *"Voiceprint saved"*.

The voiceprint is an averaged 192-number embedding saved to `~/.jarvis-os/voiceprint.json`. It is not a recording and can't be turned back into audio. Click **Re-train** any time, for example after changing microphones. To remove it, call `DELETE /api/voiceprint`.

## Tuning

| Symptom | Change |
| --- | --- |
| Jarvis sometimes ignores **you** | Lower `JARVIS_SPEAKER_THRESHOLD` (e.g. 0.22), or re-train in your usual room |
| Someone else gets through | Raise it (e.g. 0.40) |

Rejected utterances log `speaker_rejected score=…`, which helps you pick a value. Your own scores typically sit around 0.5–0.8; other people's are usually under 0.25.

!!! note
    Voice ID guards against accidental triggers, not attackers. A recording of your voice would pass.
