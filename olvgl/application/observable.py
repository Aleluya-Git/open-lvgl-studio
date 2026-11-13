"""Señales mínimas sin Qt para el ViewModel (patrón Observer)."""
from __future__ import annotations

from typing import Any, Callable


class Signal:
    def __init__(self) -> None:
        self._slots: list[Callable[..., Any]] = []
        self._blocked = 0

    def connect(self, slot: Callable[..., Any]) -> None:
        if slot not in self._slots:
            self._slots.append(slot)

    def disconnect(self, slot: Callable[..., Any]) -> None:
        if slot in self._slots:
            self._slots.remove(slot)

    def emit(self, *args: Any) -> None:
        if self._blocked:
            return
        for slot in list(self._slots):
            slot(*args)

    def block(self) -> "_Blocker":
        return _Blocker(self)


class _Blocker:
    def __init__(self, signal: Signal) -> None:
        self.signal = signal

    def __enter__(self):
        self.signal._blocked += 1
        return self

    def __exit__(self, *exc):
        self.signal._blocked -= 1
        return False
