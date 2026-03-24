"""Tests for the Rifugio Elena special refuge implementation."""

from datetime import date
from unittest.mock import MagicMock, patch

from montblanc.refuges import clear_special_registry, get_special_refuges
from montblanc.refuges.elena import Elena, _parse_check_response


class TestElenaRegistry:
    """Tests for Elena discovery and metadata via the special refuge registry."""

    def test_elena_discovered(self):
        """Rifugio Elena should be discovered by the special refuge registry."""
        clear_special_registry()
        specials = get_special_refuges()
        names = [s.refuge.name for s in specials]
        assert "Rifugio Elena" in names

    def test_elena_is_special(self):
        """The Elena refuge metadata has special=True."""
        clear_special_registry()
        specials = get_special_refuges()
        elena = next(s for s in specials if s.refuge.name == "Rifugio Elena")
        assert elena.refuge.special is True
        assert elena.refuge.id == "90002"

    def test_elena_returns_empty_on_error(self):
        """Elena returns an empty list when the API call fails."""
        clear_special_registry()
        specials = get_special_refuges()
        elena = next(s for s in specials if s.refuge.name == "Rifugio Elena")
        with patch("montblanc.refuges.elena.httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = lambda s: s
            mock_client.return_value.__exit__ = lambda s, *a: None
            mock_client.return_value.get.side_effect = RuntimeError("fail")
            result = elena.check_availability(date(2026, 7, 1), date(2026, 7, 31))
        assert result == []


class TestElenaCheckParsing:
    """Tests for _parse_check_response from the Elena booking API."""

    def test_available_many_seats(self):
        data = {
            "available": True,
            "availableBedTypes": [
                {"totalAvailableSeats": 16},
                {"totalAvailableSeats": 32},
            ],
        }
        result = _parse_check_response(data, date(2026, 7, 1))
        assert result.status == "available"
        assert result.places == 48

    def test_last_seats(self):
        data = {
            "available": True,
            "availableBedTypes": [
                {"totalAvailableSeats": 3},
            ],
        }
        result = _parse_check_response(data, date(2026, 7, 1))
        assert result.status == "last_seats"
        assert result.places == 3

    def test_last_seats_boundary(self):
        data = {
            "available": True,
            "availableBedTypes": [
                {"totalAvailableSeats": 5},
            ],
        }
        result = _parse_check_response(data, date(2026, 7, 1))
        assert result.status == "last_seats"
        assert result.places == 5

    def test_available_above_threshold(self):
        data = {
            "available": True,
            "availableBedTypes": [
                {"totalAvailableSeats": 6},
            ],
        }
        result = _parse_check_response(data, date(2026, 7, 1))
        assert result.status == "available"
        assert result.places == 6

    def test_full_when_not_available(self):
        data = {"available": False, "availableBedTypes": []}
        result = _parse_check_response(data, date(2026, 7, 1))
        assert result.status == "full"
        assert result.places == 0

    def test_full_when_zero_seats(self):
        data = {
            "available": True,
            "availableBedTypes": [
                {"totalAvailableSeats": 0},
            ],
        }
        result = _parse_check_response(data, date(2026, 7, 1))
        assert result.status == "full"
        assert result.places == 0

    def test_empty_bed_types(self):
        data = {"available": True, "availableBedTypes": []}
        result = _parse_check_response(data, date(2026, 7, 1))
        assert result.status == "full"
        assert result.places == 0

    def test_reservation_url_set(self):
        data = {
            "available": True,
            "availableBedTypes": [{"totalAvailableSeats": 10}],
        }
        result = _parse_check_response(data, date(2026, 7, 1))
        assert "booking.defav.it" in result.reservation_url

    def test_date_preserved(self):
        data = {
            "available": True,
            "availableBedTypes": [{"totalAvailableSeats": 10}],
        }
        result = _parse_check_response(data, date(2026, 8, 15))
        assert result.date == date(2026, 8, 15)

    def test_sums_across_bed_types(self):
        data = {
            "available": True,
            "availableBedTypes": [
                {"totalAvailableSeats": 16},
                {"totalAvailableSeats": 32},
                {"totalAvailableSeats": 14},
                {"totalAvailableSeats": 66},
            ],
        }
        result = _parse_check_response(data, date(2026, 7, 1))
        assert result.places == 128
        assert result.status == "available"


class TestElenaTrailData:
    """Tests for Rifugio Elena in the TMB distance table."""

    def test_elena_in_trail_data(self):
        from montblanc.trail_data import TMB_KM_FROM_START

        assert "Rifugio Elena" in TMB_KM_FROM_START

    def test_elena_distance(self):
        from montblanc.trail_data import TMB_KM_FROM_START

        assert TMB_KM_FROM_START["Rifugio Elena"] == 87.0


class TestElenaCaching:
    """Tests for Elena's 24-hour per-date disk cache."""

    def _make_elena(self) -> Elena:
        return Elena()

    def _make_mocks(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "available": True,
            "availableBedTypes": [{"totalAvailableSeats": 10}],
        }
        mock_resp.raise_for_status = MagicMock()

        mock_settings_resp = MagicMock()
        mock_settings_resp.json.return_value = {
            "openingDate": "2026-06-15",
            "closingDate": "2026-09-27",
        }
        mock_settings_resp.raise_for_status = MagicMock()
        return mock_resp, mock_settings_resp

    def test_second_call_uses_cache(self):
        """Repeated calls for the same dates should not make new API requests."""
        elena = self._make_elena()
        mock_resp, mock_settings_resp = self._make_mocks()
        disk: dict[str, object] = {}

        def fake_write(name, data):
            disk[name] = data

        def fake_read(name, max_age=0):
            return disk.get(name)

        with (
            patch("montblanc.refuges.elena.httpx.Client") as mock_client_cls,
            patch("montblanc.refuges.elena._read_disk_cache", side_effect=fake_read),
            patch("montblanc.refuges.elena._write_disk_cache", side_effect=fake_write),
        ):
            client = MagicMock()
            client.get.return_value = mock_settings_resp
            client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = lambda s: client
            mock_client_cls.return_value.__exit__ = lambda s, *a: None

            elena.check_availability(date(2026, 7, 1), date(2026, 7, 3))
            assert client.post.call_count == 3

            # Second call — should be fully cached, no new HTTP client needed.
            client.post.reset_mock()
            client.get.reset_mock()
            result = elena.check_availability(date(2026, 7, 1), date(2026, 7, 3))
            assert client.post.call_count == 0
            assert len(result) == 3

    def test_partial_cache_hit(self):
        """Only uncached dates should trigger API calls."""
        elena = self._make_elena()
        mock_resp, mock_settings_resp = self._make_mocks()
        disk: dict[str, object] = {}

        def fake_write(name, data):
            disk[name] = data

        def fake_read(name, max_age=0):
            return disk.get(name)

        with (
            patch("montblanc.refuges.elena.httpx.Client") as mock_client_cls,
            patch("montblanc.refuges.elena._read_disk_cache", side_effect=fake_read),
            patch("montblanc.refuges.elena._write_disk_cache", side_effect=fake_write),
        ):
            client = MagicMock()
            client.get.return_value = mock_settings_resp
            client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = lambda s: client
            mock_client_cls.return_value.__exit__ = lambda s, *a: None

            # Prime cache with Jul 1-2.
            elena.check_availability(date(2026, 7, 1), date(2026, 7, 2))
            assert client.post.call_count == 2

            # Now ask for Jul 1-3 — only Jul 3 should trigger a new call.
            client.post.reset_mock()
            result = elena.check_availability(date(2026, 7, 1), date(2026, 7, 3))
            assert client.post.call_count == 1
            assert len(result) == 3

    def test_cache_miss_when_read_returns_none(self):
        """When disk cache returns None (expired/missing), API should be called."""
        elena = self._make_elena()
        mock_resp, mock_settings_resp = self._make_mocks()

        with (
            patch("montblanc.refuges.elena.httpx.Client") as mock_client_cls,
            patch("montblanc.refuges.elena._read_disk_cache", return_value=None),
            patch("montblanc.refuges.elena._write_disk_cache"),
        ):
            client = MagicMock()
            client.get.return_value = mock_settings_resp
            client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = lambda s: client
            mock_client_cls.return_value.__exit__ = lambda s, *a: None

            result = elena.check_availability(date(2026, 7, 1), date(2026, 7, 1))
            assert client.post.call_count == 1
            assert len(result) == 1
