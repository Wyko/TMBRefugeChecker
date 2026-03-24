from __future__ import annotations

import importlib
import logging
import pkgutil
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

import pydantic

from montblanc.scraper import DayAvailability

logger = logging.getLogger(__name__)


class Refuge(pydantic.BaseModel):
    """A refuge along the Tour du Mont Blanc route."""

    id: str
    name: str
    special: bool = False

    order: Optional[int] = None
    """Position of the refuge along the TMB anti-clockwise route (0-indexed)."""

    km_from_start: Optional[float] = None
    """Cumulative distance in km from Les Houches along the TMB anti-clockwise route."""

    def __hash__(self) -> int:
        return hash((self.id, self.name))


class SpecialRefuge(ABC):
    """Base class for refuges not on montourdumontblanc.com.

    Subclasses must implement :meth:`check_availability` and set
    :attr:`refuge` with the static refuge metadata.
    """

    refuge: Refuge
    """The :class:`Refuge` metadata for this special refuge."""

    @abstractmethod
    def check_availability(
        self, start: date, end: date
    ) -> list[DayAvailability]:
        """Fetch availability for a date range.

        Args:
            start (date): The first date to check (inclusive).
            end (date): The last date to check (inclusive).

        Returns:
            list[DayAvailability]: Per-date availability entries.
        """


# ── Special refuge registry ────────────────────────────

_special_registry: list[SpecialRefuge] | None = None


def get_special_refuges() -> list[SpecialRefuge]:
    """Discover and return all registered special refuge instances.

    Scans the ``montblanc.refuges`` package for modules that expose a
    module-level ``special_refuge`` attribute which is a :class:`SpecialRefuge`
    instance.

    Returns:
        list[SpecialRefuge]: All discovered special refuge instances.
    """
    global _special_registry  # noqa: PLW0603
    if _special_registry is not None:
        return _special_registry

    _special_registry = []
    package = importlib.import_module(__name__)
    for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
        try:
            mod = importlib.import_module(f"{__name__}.{modname}")
        except Exception:
            logger.warning("Failed to import special refuge module %s", modname, exc_info=True)
            continue
        obj = getattr(mod, "special_refuge", None)
        if isinstance(obj, SpecialRefuge):
            _special_registry.append(obj)
    return _special_registry


def clear_special_registry() -> None:
    """Clear the cached special refuge registry (useful for testing)."""
    global _special_registry  # noqa: PLW0603
    _special_registry = None
