# Action Assist

**By Fan1337**

Action Assist is a generic green-pixel auto-click helper for Windows. It keeps the original assistive workflow, but removes the fixed Human Benchmark / browser-page assumption.

It does not embed a browser engine. It watches a pixel on the screen and clicks that same point when the pixel turns green.

## What changed

- Kept automatic screen-color detection
- Kept Win32 `SendInput` auto-clicking
- Replaced `mss` / GDI hot-loop capture with DXGI Desktop Duplication via `dxcam`
- Uses active DXGI new-frame polling in low-latency mode
- Added a slower GDI `GetPixel` fallback only for DXGI failure cases
- Removed the requirement to use Human Benchmark
- Removed the requirement to keep a browser full-screen at the screen center
- Added cursor-based target locking
- Added stronger green detection using green dominance over red and blue

## How it works

1. Run the app.
2. Turn on **AUTO CLICK**.
3. Within 3 seconds, place your cursor on the exact pixel / target area to monitor.
4. The app locks that screen coordinate.
5. When that pixel turns green, the app moves the cursor back to the locked point and clicks.

## Requirements

- Windows 10/11
- Python 3.10+

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Build

```bash
pyinstaller --onefile --windowed --icon="nl_icon.ico" --name="ActionAssist" main.py
```

## Files

```text
Action-Benchmark/
├── main.py           # Pixel-trigger assistive auto clicker
├── requirements.txt  # Runtime dependency list
├── nl_icon.ico       # App icon
└── README.md         # Project documentation
```

## Configuration

These values are defined near the top of `main.py`:

```python
GREEN_THRESHOLD = 170
GREEN_DOMINANCE = 45
RESET_THRESHOLD = 100
POST_CLICK_GUARD_SECONDS = 0.0
LOCK_DELAY_SECONDS = 3
CAPTURE_RADIUS = 0
DXGI_SPIN_YIELD_EVERY = 4096
REPOSITION_BEFORE_CLICK = False
```

Increase `GREEN_THRESHOLD` or `GREEN_DOMINANCE` if it clicks too easily. Decrease them if it misses valid green signals.
