"""Scrape refuge availability from montourdumontblanc.com.

The website renders all availability data server-side in the HTML of the
planning page.  Each refuge has a calendar grid whose cells encode status
via CSS classes on the ``dispo-case`` div:

- ``bg-primary`` — available (cell text = number of places)
- ``bg-warning`` — last seats (cell text = number of places)
- ``bg-danger``  — full or closed
- ``bg-black``   — not available for online booking
- ``bg-light``   — booking not yet open
- ``gray``       — empty padding cell

This module fetches the planning page once and parses every refuge and
its per-date availability from the returned HTML.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

import httpx
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

PLANNING_URL = "https://www.montourdumontblanc.com/en/planning"


@dataclass
class DayAvailability:
    """Availability information for a single refuge on a single date.

    Attributes:
        date: The calendar date.
        places: Number of available places, or ``None`` if unknown.
        status: One of ``"available"``, ``"last_seats"``, ``"full"``,
            ``"not_bookable"``, ``"not_open"``, or ``"closed"``.
        reservation_url: Relative URL to the reservation page, if bookable.
    """

    date: date
    places: int | None
    status: str
    reservation_url: str | None = None


@dataclass
class RefugeAvailability:
    """A refuge and its scraped availability calendar.

    Attributes:
        name: Display name of the refuge.
        slug: URL slug (e.g. ``"refuge-des-pres"``).
        numeric_id: The numeric ID extracted from ``calendarCarousel{ID}``.
        days: Per-date availability entries.
    """

    name: str
    slug: str
    numeric_id: str
    days: list[DayAvailability] = field(default_factory=list)


def _parse_month_year(header_text: str) -> tuple[int, int] | None:
    """Extract (year, month) from a calendar header like ``"mars - 2026"``.

    Args:
        header_text (str): The text content of the ``<h4>`` month header.

    Returns:
        tuple[int, int] | None: ``(year, month)`` or ``None`` if unparseable.
    """
    month_map = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
        # English variants on the site
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    text = header_text.strip().lower()
    match = re.match(r"(\w+)\s*-\s*(\d{4})", text)
    if not match:
        return None
    month_name, year_str = match.group(1), match.group(2)
    month = month_map.get(month_name)
    if month is None:
        return None
    return int(year_str), month


def _get_classes(tag: Tag) -> list[str]:
    """Return the CSS classes of a tag as a list of strings.

    Args:
        tag (Tag): A BeautifulSoup tag.

    Returns:
        list[str]: The class list, or an empty list if none.
    """
    raw = tag.get("class")
    if isinstance(raw, list):
        return [str(c) for c in raw]
    if isinstance(raw, str):
        return raw.split()
    return []


def _classify_cell(dispo_div: Tag) -> tuple[str, int | None]:
    """Determine the availability status and place count from a dispo-case div.

    Args:
        dispo_div (Tag): The ``<div class="dispo-case ...">`` element.

    Returns:
        tuple[str, int | None]: ``(status, places)`` where status is one of
            ``"available"``, ``"last_seats"``, ``"full"``, ``"not_bookable"``,
            ``"not_open"``, ``"closed"`` and places is an int or ``None``.
    """
    classes = _get_classes(dispo_div)
    text = dispo_div.get_text(strip=True)
    places = int(text) if text.isdigit() else None

    if "bg-primary" in classes:
        return "available", places
    if "bg-warning" in classes:
        return "last_seats", places
    if "bg-danger" in classes:
        return "full", None
    if "bg-black" in classes:
        return "not_bookable", None
    if "bg-light" in classes:
        return "not_open", None
    return "closed", None


def _parse_calendar_grid(
    grid: Tag, year: int, month: int,
) -> list[DayAvailability]:
    """Parse a single month grid into a list of DayAvailability.

    Args:
        grid (Tag): The ``<div class="calendar-grid">`` element.
        year (int): The year for this grid.
        month (int): The month (1–12) for this grid.

    Returns:
        list[DayAvailability]: One entry per actual calendar day found.
    """
    results: list[DayAvailability] = []

    # Each day is wrapped in either an <a> (bookable) or a bare <div class="case">
    for cell in grid.children:
        if not isinstance(cell, Tag):
            continue

        # An <a> wrapping a .case div, or a bare .case div
        if cell.name == "a":
            case_div = cell.find("div", class_="case")
            link_href = cell.get("href")
        elif cell.name == "div" and "case" in _get_classes(cell):
            case_div = cell
            link_href = None
        else:
            continue

        if not isinstance(case_div, Tag):
            continue

        # Skip header cells (Mon, Tue, ...) — they have bg-light and a bold span
        date_div = case_div.find("div", class_="date-case")
        dispo_div = case_div.find("div", class_="dispo-case")
        if not isinstance(date_div, Tag) or not isinstance(dispo_div, Tag):
            continue

        day_text = date_div.get_text(strip=True)
        if not day_text.isdigit():
            continue

        day_num = int(day_text)
        try:
            day_date = date(year, month, day_num)
        except ValueError:
            continue

        # Skip padding cells
        if "gray" in _get_classes(dispo_div):
            continue

        status, places = _classify_cell(dispo_div)

        results.append(DayAvailability(
            date=day_date,
            places=places,
            status=status,
            reservation_url=str(link_href) if link_href else None,
        ))

    return results


def _extract_name_slug(tag: Tag) -> tuple[str, str] | None:
    """Try to extract a refuge name and slug from a ``<a href="/en/refuges/...">`` tag.

    The link contains an ``<img alt="Name">`` and a
    ``<div class="fw-bold fs-5">Name</div>`` — either is used as the name.

    Args:
        tag (Tag): An ``<a>`` element pointing to a refuge page.

    Returns:
        tuple[str, str] | None: ``(name, slug)`` or ``None`` if not a refuge link.
    """
    href_val = str(tag.get("href", ""))
    slug_match = re.search(r"/en/refuges/([^/#?]+)", href_val)
    if not slug_match:
        return None

    slug = slug_match.group(1)

    # Prefer the <img alt="..."> for a clean name
    img = tag.find("img", alt=True)
    if isinstance(img, Tag):
        alt = img.get("alt")
        if alt and isinstance(alt, str) and alt.strip():
            return alt.strip(), slug

    # Fall back to the bold name div
    name_div = tag.find("div", class_="fw-bold")
    if isinstance(name_div, Tag):
        name = name_div.get_text(strip=True)
        if name:
            return name, slug

    return slug, slug


def _search_siblings_for_refuge_link(node: Tag) -> tuple[str, str] | None:
    """Search previous siblings of *node* for a refuge ``<a>`` link.

    Args:
        node (Tag): The starting tag whose previous siblings are searched.

    Returns:
        tuple[str, str] | None: ``(name, slug)`` if found, else ``None``.
    """
    for sibling in node.previous_siblings:
        if not isinstance(sibling, Tag):
            continue
        if sibling.name == "a":
            result = _extract_name_slug(sibling)
            if result:
                return result
        link = sibling.find("a", href=re.compile(r"/en/refuges/"))
        if isinstance(link, Tag):
            return _extract_name_slug(link)
    return None


def _slug_from_reservation_url(block: Tag) -> tuple[str, str] | None:
    """Extract a slug from the first reservation link inside *block*.

    Args:
        block (Tag): A carousel element that may contain reservation links.

    Returns:
        tuple[str, str] | None: ``(slug, slug)`` if found, else ``None``.
    """
    res_link = block.find("a", href=re.compile(r"/en/reservation/"))
    if not isinstance(res_link, Tag):
        return None
    href_val = str(res_link.get("href", ""))
    slug_match = re.search(r"/en/reservation/([^/]+)/", href_val)
    if slug_match:
        slug = slug_match.group(1)
        return slug, slug
    return None


def _find_refuge_info(block: Tag, numeric_id: str) -> tuple[str, str]:
    """Find the refuge name and slug from the DOM context of a carousel.

    The structure on the planning page is::

        <a class="..." href="/en/refuges/{slug}">Name...</a>
        <section>
            <div id="calendarCarousel{ID}" ...>  <- block
        </section>

    So the refuge link is a previous sibling of the carousel's parent
    ``<section>``, or a previous sibling of the carousel itself.

    As a fallback, the slug is extracted from reservation URLs inside the
    carousel.

    Args:
        block (Tag): The carousel ``<div>`` element.
        numeric_id (str): Fallback numeric ID used if no link is found.

    Returns:
        tuple[str, str]: ``(name, slug)``.
    """
    search_nodes = [block]
    if block.parent and isinstance(block.parent, Tag):
        search_nodes.append(block.parent)

    for node in search_nodes:
        result = _search_siblings_for_refuge_link(node)
        if result:
            return result

    return _slug_from_reservation_url(block) or (f"Unknown ({numeric_id})", numeric_id)


def _parse_refuge_block(block: Tag) -> RefugeAvailability | None:
    """Parse a single refuge's carousel block into a RefugeAvailability.

    Args:
        block (Tag): A ``<div id="calendarCarousel...">`` element.

    Returns:
        RefugeAvailability | None: The parsed refuge, or ``None`` if the
            block could not be parsed.
    """
    carousel_id = str(block.get("id", ""))
    id_match = re.search(r"calendarCarousel(\d+)", carousel_id)
    if not id_match:
        return None
    numeric_id = id_match.group(1)

    name, slug = _find_refuge_info(block, numeric_id)
    refuge = RefugeAvailability(name=name, slug=slug, numeric_id=numeric_id)

    for grid in block.find_all("div", class_="calendar-grid"):
        grid_parent = grid.parent
        h4 = grid_parent.find("h4") if grid_parent else None
        if not isinstance(h4, Tag):
            continue
        ym = _parse_month_year(h4.get_text())
        if ym is None:
            continue
        year, month = ym
        refuge.days.extend(_parse_calendar_grid(grid, year, month))

    return refuge


def scrape_planning() -> list[RefugeAvailability]:
    """Fetch the planning page and return all refuges with their availability.

    Makes a single HTTP GET request to the planning page and parses the
    server-rendered HTML to extract every refuge and its calendar data.

    Returns:
        list[RefugeAvailability]: All refuges found on the planning page,
            each with their per-date availability.
    """
    response = httpx.get(PLANNING_URL, timeout=30)
    response.raise_for_status()
    return parse_planning_html(response.text)


def parse_planning_html(html: str) -> list[RefugeAvailability]:
    """Parse raw planning-page HTML into refuge availability data.

    Args:
        html (str): The full HTML source of the planning page.

    Returns:
        list[RefugeAvailability]: All refuges found, each with per-date
            availability.
    """
    soup = BeautifulSoup(html, "html.parser")
    refuges: list[RefugeAvailability] = []

    carousels = soup.find_all("div", id=re.compile(r"^calendarCarousel\d+$"))
    logger.info("Found %d calendar carousels", len(carousels))

    for carousel in carousels:
        refuge = _parse_refuge_block(carousel)
        if refuge:
            refuges.append(refuge)
        else:
            logger.warning("Could not parse carousel: %s", carousel.get("id"))

    return refuges
