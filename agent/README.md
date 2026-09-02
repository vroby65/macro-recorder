# Agent guide

## Purpose and supported environment

This is a deliberately small Linux desktop macro recorder. Its Tkinter window
starts and stops global keyboard/absolute-pointer capture and loops the captured
events until stopped. Linux `evdev` supplies keyboard capture, pointer-activity
monitoring, and `uinput` playback. The Xorg backend of `pynput` supplies global
absolute pointer capture and positioning. Python 3.10 or newer, `evdev`, and
`pynput` are required.

Full native Wayland pointer support, persistence, macro editing, and non-Linux
platforms are outside the current scope.

## Project map

- `macro_recorder/app.py`: fixed Tkinter UI and idle/recording/ready/playing
  state transitions; this is the application entrypoint.
- `macro_recorder/core.py`: immutable captured/playback event models and pure
  conversion of timestamped events into a macro.
- `macro_recorder/linux_input.py`: physical-device discovery, recorder and
  pointer-monitor threads, Xorg absolute pointer events, virtual `uinput`
  device, and looping player thread.
- `macro-recorder`: executable launcher used by the user-local symbolic link.
- `tests/`: unit tests for pure event conversion and device classification.
- `pyproject.toml`: package metadata and `macro-recorder` console entrypoint.
- `README.md`: user installation, permissions, limitations, and run commands.

Runtime flow is `Tkinter command -> InputRecorder -> tuple[MacroEvent] ->
InputPlayer -> pynput/UInput`. Tkinter remains on the main thread; capture,
pointer monitoring, and playback run in worker threads.

## Invariants

- REC replaces the previous in-memory macro; PLAY loops; STOP ends either
  active operation.
- Physical devices are observed but never grabbed exclusively.
- Keyboard/button/wheel events use `EV_KEY`/`EV_REL`; pointer positions use
  absolute `ABS_X`/`ABS_Y` pairs with `SYN_REPORT` frame boundaries.
- Absolute motion, mouse buttons, and scrolling share the same `pynput`
  controller so clicks cannot race ahead of pointer positioning.
- The named virtual playback device must not be selected as a recording source.
- STOP removes its recent left-click from the recorded tail.
- Playback ignores physical pointer activity for 5 seconds, then stops on the
  first physical mouse, touchpad, or touchscreen event.
- Recording and interrupted playback must release keys/buttons left pressed.
- The GUI must never require running as root. Device access is configured
  outside the process with ACLs/groups/udev.
- Worker-thread failures return to the UI and are shown on the Tkinter thread.

## Common changes

- Change button layout or states only in `macro_recorder/app.py`.
- Change event timing/normalization in `macro_recorder/core.py` and add a focused
  unit test first.
- Change Linux device support or playback in `macro_recorder/linux_input.py`;
  keep compositor-specific code out unless the supported architecture changes.
- Update `README.md` whenever setup, permissions, UI behavior, or limitations
  change. Update this guide when architecture, invariants, paths, or validation
  commands change.

## Verification and completion

Run automated checks:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q macro_recorder tests
```

For a manual desktop check, run `python3 -m macro_recorder`, confirm the window
cannot be resized, record input in a disposable editor, move the cursor before
PLAY, and confirm clicks still land at the recorded absolute coordinates. Check
that pointer movement is ignored during the first 5 seconds of playback and
stops it afterward. Also stop during a held key. A change is complete when the
automated checks pass, the relevant manual path works, permissions are still
documented without requiring a root GUI, and the guide remains accurate.
