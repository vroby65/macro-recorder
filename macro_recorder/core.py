from dataclasses import dataclass
from typing import Iterable

from evdev import ecodes


@dataclass(frozen=True, slots=True)
class CapturedEvent:
    timestamp: float
    event_type: int
    code: int
    value: int


@dataclass(frozen=True, slots=True)
class MacroEvent:
    delay: float
    event_type: int
    code: int
    value: int


def build_macro(
    events: Iterable[CapturedEvent],
    *,
    started_at: float,
    discard_since: float | None = None,
) -> tuple[MacroEvent, ...]:
    selected = sorted(
        (
            event
            for event in events
            if discard_since is None or event.timestamp < discard_since
        ),
        key=lambda event: event.timestamp,
    )

    macro: list[MacroEvent] = []
    pressed: set[int] = set()
    previous = started_at

    for event in selected:
        macro.append(
            MacroEvent(
                delay=max(0.0, event.timestamp - previous),
                event_type=event.event_type,
                code=event.code,
                value=event.value,
            )
        )
        previous = event.timestamp

        if event.event_type == ecodes.EV_KEY:
            if event.value == 1:
                pressed.add(event.code)
            elif event.value == 0:
                pressed.discard(event.code)

    if pressed:
        for code in sorted(pressed):
            macro.append(MacroEvent(0.0, ecodes.EV_KEY, code, 0))
        macro.append(MacroEvent(0.0, ecodes.EV_SYN, ecodes.SYN_REPORT, 0))

    return tuple(macro)
