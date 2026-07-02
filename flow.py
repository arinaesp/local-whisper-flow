"""WhisperFlow — private, local voice dictation for Windows.

Hold the hotkey, speak, release. Your words are transcribed on-device
with faster-whisper and typed into whatever app has focus.
No audio or text ever leaves this machine.
"""

import json
import queue
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import keyboard
import pyperclip

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "hotkey": "right ctrl",       # hold to record, release to transcribe
    "quit_hotkey": "ctrl+alt+q",
    "model_size": "base",          # tiny | base | small | medium | large-v3
    "language": None,              # None = auto-detect, or e.g. "en", "ru"
    "remove_fillers": True,
    "paste_mode": "clipboard",     # "clipboard" (fast, reliable) or "type"
    "sample_rate": 16000,
    "input_device": None,          # None = system default microphone
}

SAMPLE_RATE = 16000

FILLER_RE = re.compile(
    r"\b(um+|uh+|erm+|hmm+|mhm+|ah+|eh+)\b[,.]?\s*",
    re.IGNORECASE,
)


def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[warn] Could not read config.json ({exc}); using defaults.")
    else:
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        print(f"[info] Wrote default config to {CONFIG_PATH}")
    return config


def clean_text(text: str, remove_fillers: bool) -> str:
    text = text.strip()
    if remove_fillers:
        text = FILLER_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


class Recorder:
    """Captures microphone audio while the hotkey is held."""

    def __init__(self, sample_rate: int, device=None):
        self.sample_rate = sample_rate
        self.device = device
        self._chunks: queue.Queue[np.ndarray] = queue.Queue()
        self._stream = None

    def start(self):
        self._chunks = queue.Queue()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._on_audio,
        )
        self._stream.start()

    def _on_audio(self, indata, frames, time_info, status):
        self._chunks.put(indata.copy())

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        chunks = []
        while not self._chunks.empty():
            chunks.append(self._chunks.get())
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).flatten()


def inject_text(text: str, mode: str):
    if mode == "type":
        keyboard.write(text, delay=0.005)
        return
    # Clipboard paste: fastest and handles unicode; restore the old clipboard.
    try:
        previous = pyperclip.paste()
    except pyperclip.PyperclipException:
        previous = None
    pyperclip.copy(text)
    time.sleep(0.05)
    keyboard.send("ctrl+v")
    time.sleep(0.15)
    if previous is not None:
        pyperclip.copy(previous)


def main():
    config = load_config()

    print("WhisperFlow — local private dictation")
    print(f"  model: {config['model_size']} (CPU, int8) — loading...")
    from faster_whisper import WhisperModel

    model = WhisperModel(config["model_size"], device="cpu", compute_type="int8")
    print("  model loaded.")
    print(f"  Hold [{config['hotkey']}] to dictate; release to insert text.")
    print(f"  Press [{config['quit_hotkey']}] to quit.")

    recorder = Recorder(config.get("sample_rate", SAMPLE_RATE), config.get("input_device"))
    busy = threading.Lock()
    stop_event = threading.Event()
    recording = threading.Event()  # guards against key auto-repeat re-firing on_press
    active_threads = []

    def transcribe_and_type(audio: np.ndarray):
        with busy:
            duration = len(audio) / config.get("sample_rate", SAMPLE_RATE)
            if duration < 0.3:
                print("  (too short, ignored)")
                return
            started = time.monotonic()
            segments, info = model.transcribe(
                audio,
                language=config["language"],
                vad_filter=True,
                beam_size=5,
            )
            text = " ".join(seg.text for seg in segments)
            text = clean_text(text, config["remove_fillers"])
            elapsed = time.monotonic() - started
            if not text:
                print("  (no speech detected)")
                return
            print(f"  [{duration:.1f}s audio, {elapsed:.1f}s transcribe] {text}")
            if stop_event.is_set():
                print("  (shutting down, discarding result instead of injecting)")
                return
            inject_text(text, config["paste_mode"])

    def on_press(_event=None):
        if stop_event.is_set() or recording.is_set() or busy.locked():
            return
        recording.set()
        print("* recording... (release to transcribe)")
        recorder.start()

    def on_release(_event=None):
        if not recording.is_set():
            return
        recording.clear()
        audio = recorder.stop()
        if stop_event.is_set():
            return  # ignore anything captured right as we're shutting down
        t = threading.Thread(target=transcribe_and_type, args=(audio,), daemon=True)
        active_threads.append(t)
        t.start()

    keyboard.on_press_key(config["hotkey"], on_press, suppress=False)
    keyboard.on_release_key(config["hotkey"], on_release, suppress=False)
    keyboard.add_hotkey(config["quit_hotkey"], stop_event.set)

    try:
        stop_event.wait()
    except KeyboardInterrupt:
        pass

    keyboard.unhook_all()
    for t in active_threads:
        t.join(timeout=10)
    print("bye.")


if __name__ == "__main__":
    main()