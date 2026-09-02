from __future__ import annotations

import os
import select
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence

from evdev import InputDevice, UInput, ecodes, list_devices
from pynput import mouse as pynput_mouse

from .core import CapturedEvent, MacroEvent, build_macro


VIRTUAL_DEVICE_NAME = "Macro Recorder Virtual Input"
POINTER_STOP_GRACE_SECONDS = 5.0
POINTER_BUTTON_CODES = {
    ecodes.BTN_LEFT,
    ecodes.BTN_RIGHT,
    ecodes.BTN_MIDDLE,
    ecodes.BTN_SIDE,
    ecodes.BTN_EXTRA,
    ecodes.BTN_FORWARD,
    ecodes.BTN_BACK,
    ecodes.BTN_TASK,
    ecodes.BTN_TOUCH,
    ecodes.BTN_TOOL_FINGER,
}
POINTER_ABSOLUTE_CODES = {
    ecodes.ABS_X,
    ecodes.ABS_Y,
    ecodes.ABS_MT_POSITION_X,
    ecodes.ABS_MT_POSITION_Y,
}
BUTTON_TO_CODE = {
    pynput_mouse.Button.left: ecodes.BTN_LEFT,
    pynput_mouse.Button.right: ecodes.BTN_RIGHT,
    pynput_mouse.Button.middle: ecodes.BTN_MIDDLE,
}
for button_name, event_code in (
    ("x1", ecodes.BTN_SIDE),
    ("x2", ecodes.BTN_EXTRA),
):
    button = getattr(pynput_mouse.Button, button_name, None)
    if button is not None:
        BUTTON_TO_CODE[button] = event_code
CODE_TO_BUTTON = {event_code: button for button, event_code in BUTTON_TO_CODE.items()}


class InputUnavailable(RuntimeError):
    pass


def is_keyboard_device(capabilities: Mapping[int, Sequence[int]]) -> bool:
    keys = set(capabilities.get(ecodes.EV_KEY, ()))
    return {ecodes.KEY_A, ecodes.KEY_ENTER, ecodes.KEY_SPACE} <= keys


def is_pointer_device(capabilities: Mapping[int, Sequence[int]]) -> bool:
    keys = set(capabilities.get(ecodes.EV_KEY, ()))
    relative_axes = set(capabilities.get(ecodes.EV_REL, ()))
    absolute_axes = set(capabilities.get(ecodes.EV_ABS, ()))

    has_relative_motion = {ecodes.REL_X, ecodes.REL_Y} <= relative_axes
    has_absolute_motion = (
        {ecodes.ABS_X, ecodes.ABS_Y} <= absolute_axes
        or {ecodes.ABS_MT_POSITION_X, ecodes.ABS_MT_POSITION_Y} <= absolute_axes
    )
    has_pointer_buttons = bool(keys & POINTER_BUTTON_CODES)
    return has_relative_motion or (has_absolute_motion and has_pointer_buttons)


def is_pointer_activity(event_type: int, code: int, value: int) -> bool:
    if event_type == ecodes.EV_REL:
        return value != 0
    if event_type == ecodes.EV_ABS:
        return code in POINTER_ABSOLUTE_CODES
    if event_type == ecodes.EV_KEY:
        return code in POINTER_BUTTON_CODES and value == 1
    return False


def needs_uinput(event: MacroEvent) -> bool:
    return event.event_type == ecodes.EV_KEY and event.code not in CODE_TO_BUTTON


def _open_devices(
    predicate: Callable[[Mapping[int, Sequence[int]]], bool],
    missing_message: str,
) -> list[InputDevice]:
    devices: list[InputDevice] = []
    denied = False

    for path in list_devices():
        try:
            device = InputDevice(path)
        except PermissionError:
            denied = True
            continue

        if device.name == VIRTUAL_DEVICE_NAME:
            device.close()
            continue

        if predicate(device.capabilities(absinfo=False)):
            devices.append(device)
        else:
            device.close()

    if devices:
        return devices

    if denied:
        raise InputUnavailable(
            "Permesso negato su /dev/input/event*. "
            "Configura l'accesso al gruppo input e riavvia la sessione."
        )
    raise InputUnavailable(missing_message)


def open_keyboard_devices() -> list[InputDevice]:
    return _open_devices(is_keyboard_device, "Nessuna tastiera rilevata.")


def open_pointer_devices() -> list[InputDevice]:
    return _open_devices(is_pointer_device, "Nessun mouse o touchpad rilevato.")


class InputRecorder:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._devices: list[InputDevice] = []
        self._events: list[CapturedEvent] = []
        self._events_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pointer_listener: pynput_mouse.Listener | None = None
        self._accept_pointer_events = False
        self._error: Exception | None = None
        self.started_at = 0.0

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> tuple[str, ...]:
        if self.active:
            raise RuntimeError("La registrazione è già attiva.")

        self._devices = open_keyboard_devices()
        self._events = []
        self._error = None
        self._stop_event.clear()
        self._accept_pointer_events = True
        self.started_at = self._clock()

        try:
            self._pointer_listener = pynput_mouse.Listener(
                on_move=self._capture_motion,
                on_click=self._capture_click,
                on_scroll=self._capture_scroll,
            )
            self._pointer_listener.start()
            self._pointer_listener.wait()
        except Exception as error:
            self._accept_pointer_events = False
            if self._pointer_listener is not None:
                self._pointer_listener.stop()
            for device in self._devices:
                device.close()
            self._devices = []
            raise InputUnavailable(
                f"Cattura delle coordinate assolute non disponibile: {error}"
            ) from error

        self._thread = threading.Thread(target=self._record, daemon=True)
        self._thread.start()
        return tuple(device.name for device in self._devices)

    def stop(self, *, discard_last_stop_click: bool = False) -> tuple[MacroEvent, ...]:
        if not self._thread:
            return ()

        stopped_at = self._clock()
        self._stop_event.set()
        self._accept_pointer_events = False
        if self._pointer_listener is not None:
            self._pointer_listener.stop()
            pointer = pynput_mouse.Controller()
            pointer.position = pointer.position
        self._thread.join()
        self._thread = None
        if self._pointer_listener is not None:
            try:
                self._pointer_listener.join(timeout=1.0)
                if self._pointer_listener.is_alive():
                    raise RuntimeError("Il listener del mouse non si è arrestato.")
            except Exception as error:
                self._error = error
            self._pointer_listener = None

        if self._error is not None:
            raise InputUnavailable(f"Lettura degli input interrotta: {self._error}")

        with self._events_lock:
            captured_events = tuple(self._events)

        discard_since = None
        if discard_last_stop_click:
            recent_limit = stopped_at - 1.0
            for event in sorted(
                captured_events,
                key=lambda captured: captured.timestamp,
                reverse=True,
            ):
                if event.timestamp < recent_limit:
                    break
                if (
                    event.event_type == ecodes.EV_KEY
                    and event.code == ecodes.BTN_LEFT
                    and event.value == 1
                ):
                    discard_since = event.timestamp
                    break

        return build_macro(
            captured_events,
            started_at=self.started_at,
            discard_since=discard_since,
        )

    def _capture_motion(self, x: int, y: int) -> None:
        self._append_pointer_frame(x, y)

    def _capture_click(
        self,
        x: int,
        y: int,
        button: pynput_mouse.Button,
        pressed: bool,
    ) -> None:
        code = BUTTON_TO_CODE.get(button)
        if code is None:
            return
        self._append_pointer_frame(x, y, ((ecodes.EV_KEY, code, int(pressed)),))

    def _capture_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        extra_events: list[tuple[int, int, int]] = []
        if dx:
            extra_events.append((ecodes.EV_REL, ecodes.REL_HWHEEL, int(dx)))
        if dy:
            extra_events.append((ecodes.EV_REL, ecodes.REL_WHEEL, int(dy)))
        self._append_pointer_frame(x, y, extra_events)

    def _append_pointer_frame(
        self,
        x: int,
        y: int,
        extra_events: Sequence[tuple[int, int, int]] = (),
    ) -> None:
        if not self._accept_pointer_events:
            return
        timestamp = self._clock()
        frame = [
            CapturedEvent(timestamp, ecodes.EV_ABS, ecodes.ABS_X, int(x)),
            CapturedEvent(timestamp, ecodes.EV_ABS, ecodes.ABS_Y, int(y)),
        ]
        frame.extend(
            CapturedEvent(timestamp, event_type, code, value)
            for event_type, code, value in extra_events
        )
        frame.append(
            CapturedEvent(timestamp, ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
        )
        with self._events_lock:
            self._events.extend(frame)

    def _record(self) -> None:
        dirty_devices: set[int] = set()

        try:
            while True:
                readable, _, _ = select.select(self._devices, (), (), 0.1)
                for device in readable:
                    try:
                        incoming = device.read()
                    except BlockingIOError:
                        continue

                    for event in incoming:
                        now = self._clock()
                        if event.type == ecodes.EV_KEY:
                            with self._events_lock:
                                self._events.append(
                                    CapturedEvent(
                                        now, event.type, event.code, event.value
                                    )
                                )
                            dirty_devices.add(device.fd)
                        elif (
                            event.type == ecodes.EV_SYN
                            and event.code == ecodes.SYN_REPORT
                            and device.fd in dirty_devices
                        ):
                            with self._events_lock:
                                self._events.append(
                                    CapturedEvent(
                                        now, event.type, event.code, event.value
                                    )
                                )
                            dirty_devices.discard(device.fd)

                if self._stop_event.is_set():
                    readable, _, _ = select.select(self._devices, (), (), 0)
                    if not readable:
                        break
        except OSError as error:
            self._error = error
        finally:
            for device in self._devices:
                device.close()
            self._devices = []


class PointerActivityMonitor:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._devices: list[InputDevice] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._armed_at = 0.0
        self._on_activity: Callable[[], None] | None = None

    def start(
        self,
        on_activity: Callable[[], None],
        grace_seconds: float = POINTER_STOP_GRACE_SECONDS,
    ) -> None:
        self._devices = open_pointer_devices()
        self._on_activity = on_activity
        self._armed_at = self._clock() + grace_seconds
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join()
        self._thread = None

    def _monitor(self) -> None:
        try:
            while not self._stop_event.is_set():
                readable, _, _ = select.select(self._devices, (), (), 0.1)
                for device in readable:
                    try:
                        incoming = device.read()
                    except BlockingIOError:
                        continue

                    for event in incoming:
                        if (
                            self._clock() >= self._armed_at
                            and is_pointer_activity(
                                event.type, event.code, event.value
                            )
                        ):
                            if self._on_activity is not None:
                                self._on_activity()
                            return
        except OSError:
            if self._on_activity is not None:
                self._on_activity()
        finally:
            for device in self._devices:
                device.close()
            self._devices = []


class InputPlayer:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pointer_monitor: PointerActivityMonitor | None = None

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        macro: Sequence[MacroEvent],
        on_finished: Callable[[Exception | None], None],
    ) -> None:
        if self.active:
            raise RuntimeError("La riproduzione è già attiva.")
        if not macro:
            raise InputUnavailable("Non c'è ancora una registrazione da riprodurre.")
        uses_uinput = any(needs_uinput(event) for event in macro)
        if uses_uinput:
            if not os.path.exists("/dev/uinput"):
                raise InputUnavailable("Il dispositivo /dev/uinput non esiste.")
            if not os.access("/dev/uinput", os.W_OK):
                raise InputUnavailable(
                    "Permesso negato su /dev/uinput. "
                    "Installa la regola udev descritta nel README."
                )

        self._stop_event.clear()
        self._pointer_monitor = PointerActivityMonitor()
        self._pointer_monitor.start(self._stop_event.set)
        self._thread = threading.Thread(
            target=self._play,
            args=(tuple(macro), on_finished),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join()
        self._thread = None

    def _play(
        self,
        macro: tuple[MacroEvent, ...],
        on_finished: Callable[[Exception | None], None],
    ) -> None:
        error: Exception | None = None
        active_keys: set[int] = set()
        active_buttons: set[pynput_mouse.Button] = set()
        virtual_input: UInput | None = None
        pointer: pynput_mouse.Controller | None = None

        try:
            capabilities: defaultdict[int, set[int]] = defaultdict(set)
            for event in macro:
                if needs_uinput(event):
                    capabilities[event.event_type].add(event.code)

            ui_capabilities = {
                event_type: sorted(codes)
                for event_type, codes in capabilities.items()
            }
            if ui_capabilities:
                virtual_input = UInput(
                    ui_capabilities,
                    name=VIRTUAL_DEVICE_NAME,
                )

            pointer = pynput_mouse.Controller()
            if virtual_input is not None and self._stop_event.wait(0.5):
                return

            while not self._stop_event.is_set():
                pending_x: int | None = None
                pending_y: int | None = None
                pending_scroll_x = 0
                pending_scroll_y = 0
                pending_buttons: list[tuple[pynput_mouse.Button, bool]] = []
                pending_uinput = False

                for event in macro:
                    if self._stop_event.wait(event.delay):
                        break

                    if event.event_type == ecodes.EV_ABS:
                        if event.code == ecodes.ABS_X:
                            pending_x = event.value
                        elif event.code == ecodes.ABS_Y:
                            pending_y = event.value
                    elif (
                        event.event_type == ecodes.EV_KEY
                        and event.code in CODE_TO_BUTTON
                    ):
                        pending_buttons.append(
                            (CODE_TO_BUTTON[event.code], event.value == 1)
                        )
                    elif event.event_type == ecodes.EV_REL:
                        if event.code == ecodes.REL_HWHEEL:
                            pending_scroll_x += event.value
                        elif event.code == ecodes.REL_WHEEL:
                            pending_scroll_y += event.value
                    elif event.event_type == ecodes.EV_SYN:
                        if pending_x is not None and pending_y is not None:
                            pointer.position = (pending_x, pending_y)
                            _ = pointer.position
                        if pending_scroll_x or pending_scroll_y:
                            pointer.scroll(pending_scroll_x, pending_scroll_y)
                        for button, pressed in pending_buttons:
                            if pressed:
                                pointer.press(button)
                                active_buttons.add(button)
                            else:
                                pointer.release(button)
                                active_buttons.discard(button)
                        if pending_uinput and virtual_input is not None:
                            virtual_input.syn()
                        pending_x = None
                        pending_y = None
                        pending_scroll_x = 0
                        pending_scroll_y = 0
                        pending_buttons = []
                        pending_uinput = False
                    elif virtual_input is not None:
                        virtual_input.write(
                            event.event_type, event.code, event.value
                        )
                        pending_uinput = True

                    if needs_uinput(event):
                        if event.value == 1:
                            active_keys.add(event.code)
                        elif event.value == 0:
                            active_keys.discard(event.code)
                else:
                    continue
                break
        except Exception as caught:
            error = caught
        finally:
            if virtual_input is not None:
                if active_keys:
                    for code in sorted(active_keys):
                        virtual_input.write(ecodes.EV_KEY, code, 0)
                    virtual_input.syn()
                virtual_input.close()
            if pointer is not None:
                for button in active_buttons:
                    pointer.release(button)
            if self._pointer_monitor is not None:
                self._pointer_monitor.stop()
                self._pointer_monitor = None
            self._thread = None
            on_finished(error)
