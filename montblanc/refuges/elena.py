"""Special refuge: Rifugio Elena.

Rifugio Elena is not part of the montourdumontblanc.com system and must be
queried separately via the AlpTrail Huts booking API at booking.defav.it.

API flow:
    1. ``GET /api/rifugio-settings`` → opening/closing season dates
    2. ``POST /api/check-availability`` (per day) → bed-type availability
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from montblanc.logic import _read_disk_cache, _write_disk_cache
from montblanc.refuges import Refuge, SpecialRefuge
from montblanc.scraper import DayAvailability

logger = logging.getLogger(__name__)

BASE_URL = "https://booking.defav.it"
BOOKING_URL = (
    "https://booking.defav.it/widget/availability"
    "?refuge_id=rifelena&color_theme=blue"
)
REFUGE_ID = "7f067747-2362-4589-ae4b-8aa584e81010"
_SETTINGS_ENDPOINT = f"{BASE_URL}/api/rifugio-settings"
_CHECK_ENDPOINT = f"{BASE_URL}/api/check-availability"
_TIMEOUT = 20
_LAST_SEATS_THRESHOLD = 5
_CACHE_TTL = 86400  # 24 hours in seconds


def _fetch_season(client: httpx.Client) -> tuple[date | None, date | None]:
    """Fetch the opening and closing dates for the current season.

    Args:
        client (httpx.Client): HTTP client to use.

    Returns:
        tuple[date | None, date | None]: ``(opening_date, closing_date)``
            parsed from the API, or ``(None, None)`` on failure.
    """
    resp = client.get(
        _SETTINGS_ENDPOINT,
        params={"refugeId": REFUGE_ID},
    )
    resp.raise_for_status()
    data = resp.json()
    opening = data.get("openingDate")
    closing = data.get("closingDate")
    try:
        opening_date = date.fromisoformat(opening) if opening else None
        closing_date = date.fromisoformat(closing) if closing else None
    except (ValueError, TypeError):
        return None, None
    return opening_date, closing_date


def _check_day(client: httpx.Client, day: date) -> DayAvailability:
    """Check availability for a single night starting on *day*.

    Args:
        client (httpx.Client): HTTP client to use.
        day (date): The check-in date.

    Returns:
        DayAvailability: Availability status for the given date.
    """
    checkout = day + timedelta(days=1)
    resp = client.post(
        _CHECK_ENDPOINT,
        json={
            "checkInDate": day.isoformat(),
            "checkOutDate": checkout.isoformat(),
            "partySize": 1,
            "boardType": "mezza_pensione",
            "refugeId": REFUGE_ID,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return _parse_check_response(data, day)


def _parse_check_response(data: dict, day: date) -> DayAvailability:
    """Convert an API check-availability response to a DayAvailability.

    Args:
        data (dict): Parsed JSON from ``POST /api/check-availability``.
        day (date): The date this response corresponds to.

    Returns:
        DayAvailability: Mapped availability entry.
    """
    if not data.get("available"):
        return DayAvailability(
            date=day, places=0, status="full", reservation_url=BOOKING_URL
        )

    total_seats = sum(
        bt.get("totalAvailableSeats", 0)
        for bt in data.get("availableBedTypes", [])
    )

    if total_seats <= 0:
        status = "full"
    elif total_seats <= _LAST_SEATS_THRESHOLD:
        status = "last_seats"
    else:
        status = "available"

    return DayAvailability(
        date=day,
        places=total_seats,
        status=status,
        reservation_url=BOOKING_URL,
    )


class Elena(SpecialRefuge):
    """Special refuge handler for Rifugio Elena."""

    refuge = Refuge(
        id="90002",
        name="Rifugio Elena",
        special=True,
    )

    def check_availability(
        self, start: date, end: date
    ) -> list[DayAvailability]:
        """Fetch availability for Rifugio Elena over a date range.

        Args:
            start (date): The first date to check (inclusive).
            end (date): The last date to check (inclusive).

        Returns:
            list[DayAvailability]: Per-date availability entries.
        """
        try:
            return self._fetch(start, end)
        except Exception:
            logger.exception("Failed to fetch Rifugio Elena availability")
            return []

    def _fetch(self, start: date, end: date) -> list[DayAvailability]:
        """Internal fetch with season filtering and per-day API calls.

        Uses per-date disk caching with a 24-hour TTL to avoid
        redundant API calls.

        Args:
            start (date): The first date to check (inclusive).
            end (date): The last date to check (inclusive).

        Returns:
            list[DayAvailability]: Per-date availability entries.
        """
        results: list[DayAvailability] = []

        # Collect dates that are not cached or stale.
        uncached: list[date] = []
        day = start
        while day <= end:
            cached = _read_disk_cache(
                f"elena_{day.isoformat()}", max_age=_CACHE_TTL
            )
            if cached is not None:
                results.append(cached)
            else:
                uncached.append(day)
            day += timedelta(days=1)

        if not uncached:
            results.sort(key=lambda d: d.date)
            return results

        with httpx.Client(timeout=_TIMEOUT) as client:
            opening, closing = self._get_season(client)

            for day in uncached:
                if opening and closing and (day < opening or day > closing):
                    avail = DayAvailability(
                        date=day,
                        places=None,
                        status="closed",
                        reservation_url=BOOKING_URL,
                    )
                else:
                    avail = _check_day(client, day)
                _write_disk_cache(f"elena_{day.isoformat()}", avail)
                results.append(avail)

        results.sort(key=lambda d: d.date)
        return results

    def _get_season(
        self, client: httpx.Client
    ) -> tuple[date | None, date | None]:
        """Return cached season dates, refreshing if stale.

        Args:
            client (httpx.Client): HTTP client to use.

        Returns:
            tuple[date | None, date | None]: ``(opening_date, closing_date)``.
        """
        cached = _read_disk_cache("elena_season", max_age=_CACHE_TTL)
        if cached is not None:
            return cached
        opening, closing = _fetch_season(client)
        _write_disk_cache("elena_season", (opening, closing))
        return opening, closing


special_refuge = Elena()
