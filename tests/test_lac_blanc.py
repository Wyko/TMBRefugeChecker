"""Tests for the Refuge du Lac Blanc special refuge implementation."""

from datetime import date
from unittest.mock import patch

from montblanc.refuges import clear_special_registry, get_special_refuges
from montblanc.refuges.du_lac_blanc import _parse_calendar_data


class TestLacBlancRegistry:
    """Tests for Lac Blanc discovery and metadata via the special refuge registry."""

    def test_lac_blanc_discovered(self):
        """Lac Blanc should be discovered by the special refuge registry."""
        clear_special_registry()
        specials = get_special_refuges()
        names = [s.refuge.name for s in specials]
        assert "Refuge du Lac Blanc" in names

    def test_lac_blanc_is_special(self):
        """The Lac Blanc refuge metadata has special=True."""
        clear_special_registry()
        specials = get_special_refuges()
        lac_blanc = next(s for s in specials if s.refuge.name == "Refuge du Lac Blanc")
        assert lac_blanc.refuge.special is True
        assert lac_blanc.refuge.id == "90001"

    def test_lac_blanc_returns_empty_on_error(self):
        """Lac Blanc returns an empty list when the API call fails."""
        clear_special_registry()
        specials = get_special_refuges()
        lac_blanc = next(s for s in specials if s.refuge.name == "Refuge du Lac Blanc")
        with patch("montblanc.refuges.du_lac_blanc._get_token", side_effect=RuntimeError("fail")):
            result = lac_blanc.check_availability(date(2026, 7, 1), date(2026, 7, 31))
        assert result == []


class TestLacBlancCalendarParsing:
    """Tests for _parse_calendar_data from the Lac Blanc API response."""

    SAMPLE_DATA = {
        "calendar_status": "reservations-open",
        "dates_array": [
            {
                "month": "July",
                "days": [
                    {"date": "01/07/2026", "spaces": 30, "date_status": "active"},
                    {"date": "02/07/2026", "spaces": 3, "date_status": "active"},
                    {"date": "03/07/2026", "spaces": 0, "date_status": "active"},
                    {"date": "15/07/2026", "spaces": 20, "date_status": "active"},
                ],
            },
            {
                "month": "August",
                "days": [
                    {"date": "01/08/2026", "spaces": 10, "date_status": "active"},
                ],
            },
        ],
    }

    def test_filters_by_date_range(self):
        result = _parse_calendar_data(
            self.SAMPLE_DATA, date(2026, 7, 1), date(2026, 7, 3)
        )
        assert len(result) == 3
        assert result[0].date == date(2026, 7, 1)
        assert result[-1].date == date(2026, 7, 3)

    def test_excludes_dates_outside_range(self):
        result = _parse_calendar_data(
            self.SAMPLE_DATA, date(2026, 7, 10), date(2026, 7, 20)
        )
        assert len(result) == 1
        assert result[0].date == date(2026, 7, 15)

    def test_spans_multiple_months(self):
        result = _parse_calendar_data(
            self.SAMPLE_DATA, date(2026, 7, 1), date(2026, 8, 31)
        )
        assert len(result) == 5

    def test_available_status_for_many_spaces(self):
        result = _parse_calendar_data(
            self.SAMPLE_DATA, date(2026, 7, 1), date(2026, 7, 1)
        )
        assert result[0].status == "available"
        assert result[0].places == 30

    def test_last_seats_status_for_few_spaces(self):
        result = _parse_calendar_data(
            self.SAMPLE_DATA, date(2026, 7, 2), date(2026, 7, 2)
        )
        assert result[0].status == "last_seats"
        assert result[0].places == 3

    def test_not_bookable_status_for_zero_spaces(self):
        result = _parse_calendar_data(
            self.SAMPLE_DATA, date(2026, 7, 3), date(2026, 7, 3)
        )
        assert result[0].status == "not_bookable"
        assert result[0].places == 0

    def test_reservation_url_set(self):
        result = _parse_calendar_data(
            self.SAMPLE_DATA, date(2026, 7, 1), date(2026, 7, 1)
        )
        assert result[0].reservation_url == "https://refugelacblanc.com/en/"

    def test_closed_status_returns_empty(self):
        closed_data = {"calendar_status": "reservations-closed", "dates_array": []}
        result = _parse_calendar_data(closed_data, date(2026, 7, 1), date(2026, 7, 31))
        assert result == []

    def test_sorted_by_date(self):
        result = _parse_calendar_data(
            self.SAMPLE_DATA, date(2026, 7, 1), date(2026, 8, 31)
        )
        dates = [d.date for d in result]
        assert dates == sorted(dates)

    def test_handles_malformed_day_entry(self):
        data = {
            "calendar_status": "reservations-open",
            "dates_array": [
                {"month": "July", "days": [
                    {"date": "invalid", "spaces": 10, "date_status": "active"},
                    {"date": "01/07/2026", "spaces": 10, "date_status": "active"},
                ]},
            ],
        }
        result = _parse_calendar_data(data, date(2026, 7, 1), date(2026, 7, 31))
        assert len(result) == 1
        assert result[0].date == date(2026, 7, 1)

    def test_empty_dates_array(self):
        data = {"calendar_status": "reservations-open", "dates_array": []}
        result = _parse_calendar_data(data, date(2026, 7, 1), date(2026, 7, 31))
        assert result == []
