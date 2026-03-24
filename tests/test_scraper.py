"""Tests for the HTML scraper — parsing availability data from planning page HTML."""

from datetime import date

import pytest
from bs4 import BeautifulSoup, Tag

from montblanc.scraper import (
    DayAvailability,
    RefugeAvailability,
    _classify_cell,
    _parse_calendar_grid,
    _parse_month_year,
    parse_planning_html,
)


# ── _parse_month_year ───────────────────────────────────


class TestParseMonthYear:
    """Tests for extracting year/month from calendar header text."""

    def test_french_month(self):
        assert _parse_month_year("mars - 2026") == (2026, 3)

    def test_english_month(self):
        assert _parse_month_year("july - 2026") == (2026, 7)

    def test_accented_french(self):
        assert _parse_month_year("février - 2025") == (2025, 2)

    def test_case_insensitive(self):
        assert _parse_month_year("JUIN - 2026") == (2026, 6)

    def test_extra_whitespace(self):
        assert _parse_month_year("  août  -  2026  ") == (2026, 8)

    def test_invalid_month(self):
        assert _parse_month_year("foobar - 2026") is None

    def test_no_year(self):
        assert _parse_month_year("mars") is None

    def test_empty_string(self):
        assert _parse_month_year("") is None

    def test_december(self):
        assert _parse_month_year("décembre - 2025") == (2025, 12)

    def test_all_french_months(self):
        months = [
            ("janvier", 1), ("février", 2), ("mars", 3), ("avril", 4),
            ("mai", 5), ("juin", 6), ("juillet", 7), ("août", 8),
            ("septembre", 9), ("octobre", 10), ("novembre", 11), ("décembre", 12),
        ]
        for name, expected in months:
            assert _parse_month_year(f"{name} - 2026") == (2026, expected)


# ── _classify_cell ──────────────────────────────────────


def _make_dispo_div(classes: str, text: str = "") -> Tag:
    """Build a minimal <div class="dispo-case ...">text</div> Tag.

    Args:
        classes: Space-separated CSS classes.
        text: Inner text of the div.

    Returns:
        Tag: A BeautifulSoup Tag element.
    """
    html = f'<div class="{classes}">{text}</div>'
    return BeautifulSoup(html, "html.parser").div  # type: ignore[return-value]


class TestClassifyCell:
    """Tests for mapping CSS classes to availability status."""

    def test_available(self):
        div = _make_dispo_div("dispo-case bg-primary", "12")
        assert _classify_cell(div) == ("available", 12)

    def test_last_seats(self):
        div = _make_dispo_div("dispo-case bg-warning", "3")
        assert _classify_cell(div) == ("last_seats", 3)

    def test_full(self):
        div = _make_dispo_div("dispo-case bg-danger", "")
        assert _classify_cell(div) == ("full", None)

    def test_not_bookable(self):
        div = _make_dispo_div("dispo-case bg-black", "")
        assert _classify_cell(div) == ("not_bookable", None)

    def test_not_open(self):
        div = _make_dispo_div("dispo-case bg-light", "")
        assert _classify_cell(div) == ("not_open", None)

    def test_closed_unknown_class(self):
        div = _make_dispo_div("dispo-case", "")
        assert _classify_cell(div) == ("closed", None)

    def test_available_no_text(self):
        div = _make_dispo_div("dispo-case bg-primary", "")
        assert _classify_cell(div) == ("available", None)


# ── _parse_calendar_grid ────────────────────────────────


def _build_grid_html(cells: list[dict]) -> str:
    """Build a calendar-grid HTML fragment from cell descriptors.

    Args:
        cells: List of dicts with keys 'day', 'dispo_class', 'places',
            and optional 'link'.

    Returns:
        str: An HTML string for a calendar-grid div.
    """
    parts = ['<div class="calendar-grid">']
    for cell in cells:
        case_html = (
            f'<div class="case">'
            f'<div class="date-case">{cell["day"]}</div>'
            f'<div class="dispo-case {cell["dispo_class"]}">{cell.get("places", "")}</div>'
            f'</div>'
        )
        if cell.get("link"):
            parts.append(f'<a href="{cell["link"]}">{case_html}</a>')
        else:
            parts.append(case_html)
    parts.append("</div>")
    return "".join(parts)


class TestParseCalendarGrid:
    """Tests for parsing a month grid into DayAvailability entries."""

    def test_single_available_day(self):
        html = _build_grid_html([
            {"day": "15", "dispo_class": "bg-primary", "places": "8"},
        ])
        grid = BeautifulSoup(html, "html.parser").find("div", class_="calendar-grid")
        results = _parse_calendar_grid(grid, 2026, 7)
        assert len(results) == 1
        assert results[0].date == date(2026, 7, 15)
        assert results[0].status == "available"
        assert results[0].places == 8

    def test_multiple_days(self):
        html = _build_grid_html([
            {"day": "1", "dispo_class": "bg-primary", "places": "10"},
            {"day": "2", "dispo_class": "bg-warning", "places": "2"},
            {"day": "3", "dispo_class": "bg-danger", "places": ""},
        ])
        grid = BeautifulSoup(html, "html.parser").find("div", class_="calendar-grid")
        results = _parse_calendar_grid(grid, 2026, 6)
        assert len(results) == 3
        assert results[0].status == "available"
        assert results[1].status == "last_seats"
        assert results[1].places == 2
        assert results[2].status == "full"

    def test_skips_gray_padding(self):
        html = _build_grid_html([
            {"day": "30", "dispo_class": "gray", "places": ""},
            {"day": "1", "dispo_class": "bg-primary", "places": "5"},
        ])
        grid = BeautifulSoup(html, "html.parser").find("div", class_="calendar-grid")
        results = _parse_calendar_grid(grid, 2026, 7)
        assert len(results) == 1
        assert results[0].date == date(2026, 7, 1)

    def test_reservation_url_from_link(self):
        html = _build_grid_html([
            {
                "day": "10",
                "dispo_class": "bg-primary",
                "places": "6",
                "link": "/en/reservation/refuge-du-lac-blanc/2026-07-10",
            },
        ])
        grid = BeautifulSoup(html, "html.parser").find("div", class_="calendar-grid")
        results = _parse_calendar_grid(grid, 2026, 7)
        assert results[0].reservation_url == "/en/reservation/refuge-du-lac-blanc/2026-07-10"

    def test_no_reservation_url_when_no_link(self):
        html = _build_grid_html([
            {"day": "5", "dispo_class": "bg-danger", "places": ""},
        ])
        grid = BeautifulSoup(html, "html.parser").find("div", class_="calendar-grid")
        results = _parse_calendar_grid(grid, 2026, 7)
        assert results[0].reservation_url is None

    def test_invalid_day_skipped(self):
        html = _build_grid_html([
            {"day": "Mon", "dispo_class": "bg-light", "places": ""},
        ])
        grid = BeautifulSoup(html, "html.parser").find("div", class_="calendar-grid")
        results = _parse_calendar_grid(grid, 2026, 7)
        assert results == []


# ── parse_planning_html (integration) ───────────────────


def _build_planning_html(refuges: list[dict]) -> str:
    """Build a minimal planning page HTML with refuge carousels.

    Args:
        refuges: List of dicts with keys 'numeric_id', 'name', 'slug',
            and 'cells' (list of cell dicts for _build_grid_html).

    Returns:
        str: Full HTML page string.
    """
    parts = ["<html><body>"]
    for r in refuges:
        # Refuge link (sibling of section)
        parts.append(
            f'<a href="/en/refuges/{r["slug"]}">'
            f'<img alt="{r["name"]}">'
            f'</a>'
        )
        # Calendar carousel in a section
        parts.append("<section>")
        parts.append(f'<div id="calendarCarousel{r["numeric_id"]}">')
        # One month grid
        parts.append('<div><h4>july - 2026</h4>')
        parts.append(_build_grid_html(r["cells"]))
        parts.append("</div>")
        parts.append("</div>")
        parts.append("</section>")
    parts.append("</body></html>")
    return "".join(parts)


class TestParsePlanningHtml:
    """Integration tests for parsing a full planning page."""

    def test_single_refuge(self):
        html = _build_planning_html([{
            "numeric_id": "99",
            "name": "Refuge du Lac Blanc",
            "slug": "refuge-du-lac-blanc",
            "cells": [
                {"day": "1", "dispo_class": "bg-primary", "places": "14"},
                {"day": "2", "dispo_class": "bg-warning", "places": "3"},
            ],
        }])
        result = parse_planning_html(html)
        assert len(result) == 1
        refuge = result[0]
        assert refuge.numeric_id == "99"
        assert refuge.name == "Refuge du Lac Blanc"
        assert refuge.slug == "refuge-du-lac-blanc"
        assert len(refuge.days) == 2
        assert refuge.days[0].places == 14
        assert refuge.days[1].status == "last_seats"

    def test_multiple_refuges(self):
        html = _build_planning_html([
            {
                "numeric_id": "10",
                "name": "Refuge de Nant Borrant",
                "slug": "refuge-de-nant-borrant",
                "cells": [{"day": "5", "dispo_class": "bg-primary", "places": "20"}],
            },
            {
                "numeric_id": "11",
                "name": "Refuge du Lac Blanc",
                "slug": "refuge-du-lac-blanc",
                "cells": [{"day": "5", "dispo_class": "bg-danger", "places": ""}],
            },
        ])
        result = parse_planning_html(html)
        assert len(result) == 2
        ids = {r.numeric_id for r in result}
        assert ids == {"10", "11"}

    def test_empty_page(self):
        result = parse_planning_html("<html><body></body></html>")
        assert result == []
