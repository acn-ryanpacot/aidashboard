<#
.SYNOPSIS
  EXPERIMENTAL: bundle the Python core service into a self-contained folder
  so the Tauri installer can ship it (no uv/Python needed on the target PC).

.DESCRIPTION
  Builds services/core with PyInstaller (one-folder mode, so the desktop app
  can stop the process cleanly) and copies the result to
  apps/desktop/src-tauri/binaries/jarvis-core. Then build the installer with:

      pnpm --filter @jarvis/desktop tauri build --config src-tauri/tauri.bundle-core.conf.json

  The bundle includes PyTorch and is several GB. Models are still downloaded
  on first run into the Hugging Face cache. For a personal PC, the default
  (the app launches the core from your checkout) is simpler and recommended.

.PARAMETER Torch
  "cu128" (NVIDIA GPU, default) or "cpu".
#>
param(
  [ValidateSet("cu128", "cpu")]
  [string]$Torch = "cu128"
)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path "$PSScriptRoot\.."
$core = Join-Path $repo "services\core"
$target = Join-Path $repo "apps\desktop\src-tauri\binaries\jarvis-core"

Push-Location $core
try {
  uv sync --group dev --extra voice --extra speaker --extra mcp --extra $Torch
  uv run --with pyinstaller pyinstaller `
    --noconfirm --clean --onedir --name jarvis-core `
    --paths src `
    --collect-all kokoro --collect-all misaki --collect-all espeakng_loader `
    --collect-all openwakeword --collect-all faster_whisper --collect-all ctranslate2 `
    --collect-all speechbrain --collect-all silero_vad --collect-all webrtcvad `
    --collect-all recurring_ical_events --collect-all icalendar `
    --copy-metadata torch --copy-metadata tqdm --copy-metadata regex `
    --copy-metadata requests --copy-metadata packaging --copy-metadata filelock `
    --copy-metadata numpy --copy-metadata tokenizers --copy-metadata huggingface-hub `
    src\jarvis_core\__main__.py

  if (Test-Path $target) { Remove-Item -Recurse -Force $target }
  New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
  Copy-Item -Recurse -Force "dist\jarvis-core" $target
  Write-Host "Bundled core copied to $target" -ForegroundColor Green
  Write-Host "Smoke test: & '$target\jarvis-core.exe'  (then open http://127.0.0.1:8765/api/health)"
}
finally {
  Pop-Location
}
