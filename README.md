# WhisperFlow — private, local voice dictation

A Wispr Flow–style dictation tool that runs **entirely on your machine**. Hold a
hotkey, speak, release — your words appear at the cursor in whatever app has
focus. No cloud, no account, no audio or text ever leaves your computer.

Built to answer one question: can you get Wispr Flow's push-to-talk dictation
experience without the cloud round-trip? The answer is yes for transcription
and cleanup — the one piece that genuinely needs a cloud LLM is per-app tone
matching, which is deliberately out of scope for v1.

## How Wispr Flow works (and what this replicates)

Wispr Flow's pipeline, based on public documentation and reviews:

1. **Global hotkey** (hold-to-talk) captures microphone audio locally.
2. Audio is **sent to cloud servers** for ASR (speech recognition).
3. Cloud **LLM post-processing** removes filler words, fixes punctuation, and
   adapts tone to the active app (casual for Slack, formal for email).
4. The formatted text is sent back and **injected at the cursor**.

Steps 2–3 are why Wispr Flow requires a constant internet connection and why
your speech — plus screen context — transits their servers.

## This local version

| Stage | Wispr Flow | WhisperFlow (this app) |
|---|---|---|
| Hotkey capture | local | local (`keyboard`, push-to-talk) |
| Speech recognition | cloud ASR | **on-device** faster-whisper (CTranslate2, CPU int8) |
| Cleanup | cloud LLM | local rules: filler-word removal, spacing, capitalization |
| Text insertion | local | local (clipboard paste or simulated typing) |
| Tone matching per app | cloud LLM | not implemented — the one piece that needs an LLM; a local Ollama model could fill this in later |

The only thing that touches the network is a **one-time model download** from
Hugging Face on first run (cached in `~\.cache\huggingface`). After that it's
fully offline.

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
| `model_size` | `base` | `tiny` (fastest) → `large-v3` (most accurate). `small` is a good CPU sweet spot, though it's a heavier load — see engineering notes |
| `language` | `null` | Auto-detect; set `"en"`, `"ru"`, etc. to skip detection, speed up, and improve accuracy |
| `remove_fillers` | `true` | Strips um/uh/erm etc. |
| `paste_mode` | `clipboard` | `clipboard` pastes via Ctrl+V (fast, unicode-safe, restores old clipboard); `type` simulates keystrokes instead |
| `input_device` | `null` | System default mic; set a device index from `python -m sounddevice` |

## Engineering notes

**Shutdown race condition.** The first working version transcribed in a
background thread and injected text immediately on completion, with no check
for whether the app was still running. Quitting mid-transcription — e.g.
holding the hotkey a few more times right before pressing quit — could let a
background thread finish *after* the main process had already exited and
focus had returned to whatever window was active, typically the terminal.
The transcribed text would then get typed into that window, which if it's a
shell, means arbitrary transcribed speech gets interpreted as commands.

Fixed by:
- Guarding `on_press`/`on_release` so no new recording starts once shutdown
  begins.
- Checking the shutdown flag immediately before text injection and discarding
  the result if it's set.
- Joining all in-flight worker threads before the process exits, so nothing
  outlives the window it was meant to type into.

**Resource sizing.** The `small` model caused a brief full system freeze on
this machine while downloading + loading concurrently over a constrained
mobile connection. `base` runs comfortably faster than real-time on CPU
(int8 quantization) and was kept as the practical default; `small`/`medium`
are viable with more headroom.

## Privacy and security properties

- Audio is held in RAM only; never written to disk.
- Transcripts are printed to the console and typed at the cursor — never
  logged or written to a file. Verified by inspecting every `open()`/`write()`
  call in the codebase.
- No telemetry, no network calls at runtime, after the model is cached.
- The system clipboard briefly holds the dictated text during paste-mode
  injection (well under a second) before the previous clipboard contents are
  restored. Anything else actively polling the clipboard during that window
  could theoretically read it — low risk for personal use, worth knowing if
  dictating something sensitive. Use `paste_mode: "type"` to avoid the
  clipboard entirely, at the cost of speed.
- The `keyboard` library requires a system-wide keyboard hook to detect the
  push-to-talk key regardless of which window has focus. This is inherent to
  how global hotkeys work on Windows, not something specific to this app —
  worth knowing before running any tool that registers global hotkeys.

## Architecture

```
flow.py
├── Recorder        — captures mic audio while hotkey is held (sounddevice)
├── clean_text()     — filler removal, spacing, capitalization
├── inject_text()    — clipboard-paste or simulated-typing output
└── main()
    ├── loads config.json (falls back to defaults, writes file on first run)
    ├── loads faster-whisper model (CPU, int8)
    ├── registers push-to-talk + quit hotkeys
    └── on release: transcribe in a background thread, inject if still running
```
