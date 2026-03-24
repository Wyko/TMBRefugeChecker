"""Special refuge: Refuge du Lac Blanc.

Lac Blanc is not part of the montourdumontblanc.com system and must be
queried separately via its own WordPress REST API at refugelacblanc.com.

API flow:
    1. ``GET /wp-json/reservation/v1/getpublictoken`` → JWT bearer token
    2. ``GET /wp-json/reservation/v1/getcalendardata`` (with bearer) →
       calendar status and per-day availability (spaces + status)
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import httpx

from montblanc.refuges import Refuge, SpecialRefuge
from montblanc.scraper import DayAvailability

logger = logging.getLogger(__name__)

BASE_URL = "https://refugelacblanc.com"
BOOKING_URL = "https://refugelacblanc.com/en/"
_TOKEN_ENDPOINT = f"{BASE_URL}/wp-json/reservation/v1/getpublictoken"
_CALENDAR_ENDPOINT = f"{BASE_URL}/wp-json/reservation/v1/getcalendardata"
_TIMEOUT = 20


def _get_token() -> str:
    """Fetch a public JWT token from the Lac Blanc booking API.

    Returns:
        str: The bearer token.

    Raises:
        RuntimeError: If the token request fails.
    """
    resp = httpx.get(_TOKEN_ENDPOINT, follow_redirects=True, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["content"]["token"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"Unexpected token response: {data}") from exc


def _fetch_calendar(token: str) -> dict:
    """Fetch calendar data using a bearer token.

    Args:
        token (str): JWT bearer token.

    Returns:
        dict: The parsed JSON response containing ``calendar_status``
            and ``dates_array``.

    Raises:
        RuntimeError: If the calendar request fails.
    """
    resp = httpx.get(
        _CALENDAR_ENDPOINT,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        follow_redirects=True,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _parse_calendar_data(
    data: dict, start: date, end: date
) -> list[DayAvailability]:
    """Parse the calendar API response into DayAvailability entries.

    Args:
        data (dict): Raw API response with ``calendar_status`` and
            ``dates_array``.
        start (date): First date to include (inclusive).
        end (date): Last date to include (inclusive).

    Returns:
        list[DayAvailability]: Availability entries within the date range,
            sorted by date.
    """
    status = data.get("calendar_status", "")
    if status == "reservations-closed":
        return []

    results: list[DayAvailability] = []
    for month_block in data.get("dates_array", []):
        for day in month_block.get("days", []):
            try:
                day_date = datetime.strptime(day["date"], "%d/%m/%Y").date()
            except (KeyError, ValueError):
                continue

            if day_date < start or day_date > end:
                continue

            spaces = day.get("spaces")
            day_status = day.get("date_status", "")

            if day_status == "active":
                if spaces is not None and spaces <= 0:
                    avail_status = "not_bookable"
                elif spaces is not None and spaces <= 5:
                    avail_status = "last_seats"
                elif spaces is not None and spaces > 5:
                    avail_status = "available"
                else:
                    avail_status = "not_bookable"
            else:
                avail_status = "closed"

            results.append(
                DayAvailability(
                    date=day_date,
                    places=spaces,
                    status=avail_status,
                    reservation_url=BOOKING_URL,
                )
            )

    results.sort(key=lambda d: d.date)
    return results


class LacBlanc(SpecialRefuge):
    """Special refuge handler for Refuge du Lac Blanc."""

    refuge = Refuge(
        id="90001",
        name="Refuge du Lac Blanc",
        special=True,
    )

    def check_availability(
        self, start: date, end: date
    ) -> list[DayAvailability]:
        """Fetch availability for Lac Blanc over a date range.

        Args:
            start (date): The first date to check (inclusive).
            end (date): The last date to check (inclusive).

        Returns:
            list[DayAvailability]: Per-date availability entries.
        """
        try:
            token = _get_token()
            data = _fetch_calendar(token)
            return _parse_calendar_data(data, start, end)
        except Exception:
            logger.exception("Failed to fetch Lac Blanc availability")
            return []


special_refuge = LacBlanc()
