# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A PyQt5 desktop GUI tool for chess arbiters. It monitors PGN files (local or web URLs) in real-time and detects draw conditions per FIDE rules: 3-Fold Repetition, 5-Fold Repetition, 50 Moves Rule, and 75 Moves Rule. When a claim is detected, the result appears in a table and a desktop notification fires. Supports macOS and Windows.

## Running the App

```bash
python main.py
```

## Installing Dependencies

**Windows:**
```bash
pip install -r requirments-win.txt -r requirments.txt
```

**macOS:**
```bash
pip install -r requirments-macos.txt -r requirments.txt
```

## Building Distributables

Run from the `build/` directory:

```bash
# Windows
pyinstaller windows.spec

# macOS
pyinstaller mac.spec
```

## Architecture

The app follows a strict MVC pattern with two separate MVC stacks.

**Main window MVC:**
- `ChessClaimController` (in `src/controllers.py`) — subclasses `QApplication`; owns all workers and coordinates the scan lifecycle
- `ChessClaimView` (in `src/views/main_view.py`) — the main `QMainWindow`; handles the claims table, status bar, and OS notifications
- `Claims` (in `src/models/claims.py`) — pure domain logic; uses `python-chess` to detect draw conditions in a `Game` object

**Source dialog MVC:**
- `SourceDialogController` (in `src/controllers.py`) — manages source entry, validation, and persistence to `sources.json`
- `AddSourceDialog` / `SourceHBox` (in `src/views/dialog_view.py`) — dialog UI for adding local file paths or URLs

**Worker threads** (`src/models/workers.py`) — all background work runs here:
- `MakePgn` — combines all source PGN files into a single `games.pgn` in the app data directory; runs every 4 seconds via a `threading.Thread`
- `DownloadGames` — downloads URL-based PGN sources; runs every 4 seconds via `QThread`
- `Scan` — polls `games.pgn` for size changes, then calls `Claims.check_game()` on each game; emits `add_entry_signal` per finding; runs every 4 seconds via `QThread`
- `Stop` — coordinates graceful teardown of all worker threads via a shared `threading.Event`
- `CheckDownload` — validates a URL source; runs via `QThreadPool` (`QRunnable`)

**Thread coordination:** `MakePgn` and `Scan` share a `threading.Lock` so they don't read/write `games.pgn` simultaneously. The `stop_event` (`threading.Event`) is shared across all long-running workers; setting it causes each to exit its polling loop after the current iteration.

**Persistence:** App data (combined `games.pgn`, `sources.json`) is stored in the OS app data directory (`%APPDATA%\Chess Claim Tool` on Windows, `~/Library/Application Support/Chess Claim Tool` on macOS) — resolved by `get_appdata_path()` in `src/helpers.py`.

**Resource loading:** `resource_path()` in `src/helpers.py` resolves icon and CSS paths for both normal execution and PyInstaller bundles (`sys._MEIPASS`).

**OS notifications:** Platform-checked at import time in `main_view.py`. macOS uses `src/notifications/mac.py`; Windows uses the `windows_toasts` package.
