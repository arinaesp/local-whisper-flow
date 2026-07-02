# WhisperFlow — private, local voice dictation

A Wispr Flow–style dictation tool that runs **entirely on your machine**. Hold a
hotkey, speak, release — your words appear at the cursor in whatever app has
focus. No cloud, no account, no audio or text ever leaves your computer.

## How Wispr Flow works (and what we replicate)

Wispr Flow's pipeline, based on public documentation and reviews:

1. **Global hotkey** (hold-to-talk) captures microphone audio locally.
2. Audio is **sent to cloud servers** for ASR (speech recognition).
3. Cloud **LLM post-processing** removes filler words, fixes punctuation, and
   adapts tone to the active app (casual for Slack, formal for email).
4. The formatted text is sent back and **injected at the cursor**.

Steps 2–3 are why Wispr Flow requires a constant internet connection and why
your speech (plus screen context) transits their servers.

## This local version

| Stage | Wispr Flow | WhisperFlow (this app) |
|---|---|---|
| Hotkey capture | local | local (`keyboard`, push-to-talk) |
| Speech recognition | cloud ASR | **on-device** faster-whisper (CTranslate2, CPU int8) |
| Cleanup | cloud LLM | local rules: filler-word removal, spacing, capitalization |
| Text insertion | local | local (clipboard paste or simulated typing) |

The one thing that touches the network is a **one-time model download** from
Hugging Face on first run (cached in `~\.cache\huggingface`). After that it is
fully offline. Tone-matching by app is deliberately out of scope for v1 — it's
the piece that needs an LLM; a local Ollama model could be added later.

## Setup

```powershell
pip install -r requirements.txt
python flow.py
```

First run downloads the Whisper model (~145 MB for `base`) and writes
`config.json` with defaults.

## Usage

- **Hold `Right Ctrl`**, speak, **release** → text is typed at your cursor.
- **`Ctrl+Alt+Q`** quits.

## Configuration (`config.json`)

| Key | Default | Notes |
|---|---|---|
| `hotkey` | `right ctrl` | Push-to-talk key (any `keyboard` lib key name) |
| `model_size` | `base` | `tiny` (fastest) → `large-v3` (most accurate). `small` is a good CPU sweet spot |
| `language` | `null` | Auto-detect; set `"en"`, `"ru"`, etc. to skip detection and speed up |
| `remove_fillers` | `true` | Strips um/uh/erm etc. |
| `paste_mode` | `clipboard` | `clipboard` pastes via Ctrl+V (fast, unicode-safe, restores old clipboard); `type` simulates keystrokes |
| `input_device` | `null` | System default mic; set a device index from `python -m sounddevice` |

## Privacy properties

- Audio is held in RAM only; never written to disk.
- Transcripts are printed to your console and typed at the cursor — not logged.
- No telemetry, no network calls at runtime (after the model is cached).
