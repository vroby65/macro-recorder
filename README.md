# Macro Recorder

A small Linux window with three buttons:

- `● REC` clears the previous macro and starts recording immediately;
- `▶ PLAY` replays the macro in a loop; after 5 seconds, any pointer movement,
  click, or physical touch stops playback;
- `■ STOP` stops recording or playback.

Mouse positions are recorded as absolute coordinates and replayed at the same
point regardless of the cursor's starting position. Keyboard and stop
monitoring use `evdev`. The keyboard is replayed through `uinput`; position,
clicks, and scrolling share `pynput`'s Xorg controller.

Capture and absolute global positioning use `pynput`'s Xorg backend. On pure
Wayland, global pointer access is intentionally limited: through XWayland it
may work only partially and depends on the compositor.

## Installation

On Linux Mint, Ubuntu, or Debian:

```bash
sudo apt install python3-evdev python3-pynput python3-tk
```

Alternatively, using a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Direct launch from the project folder:

```bash
python3 -m macro_recorder
./macro-recorder
```

After installing with `pip`, the command is also available as:

```bash
macro-recorder
```

## Linux permissions

The application must be able to read `/dev/input/event*` and write to
`/dev/uinput`. First try launching it normally: some distributions already
assign the necessary ACLs to the session user.

If access is missing, on distributions that use the `input` group:

```bash
sudo usermod -aG input "$USER"
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/70-macro-recorder-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput
```

Then log out and back in. Do not run the interface with `sudo`. Membership in
the `input` group allows reading all session inputs, including passwords:
grant it only to trusted users and programs.

## Intentional limitations

- Absolute pointer recording requires an Xorg session; pure Wayland is not
  fully supported.
- The macro stays in memory and is lost when closing the application.
- Changing resolution or monitor layout after recording can shift the expected
  coordinates.
- The click used on the STOP button is automatically removed from the end of
  the recording.

## Verification

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q macro_recorder tests
```
