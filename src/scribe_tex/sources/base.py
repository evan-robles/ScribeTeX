"""NoteSource protocol and registry."""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

@runtime_checkable
class NoteSource(Protocol):
    def fetch_pages(self, ref: str) -> list[Path]:
        """Return page images (PNG paths) for the given source reference."""
        ...

_REGISTRY: dict[str, Callable[[], NoteSource]] = {}


def register(name: str, factory: Callable[[], NoteSource]) -> None:
    _REGISTRY[name] = factory


def get_source(name: str) -> NoteSource:
    if name not in _REGISTRY:
        raise ValueError(f"unknown note source: {name!r}")
    return _REGISTRY[name]()
