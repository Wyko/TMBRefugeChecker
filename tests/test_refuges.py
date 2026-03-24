"""Tests for the Refuge model, trail distance data, and special refuge framework."""

from datetime import date, timedelta
from unittest.mock import patch

from montblanc.refuges import Refuge, SpecialRefuge, clear_special_registry, get_special_refuges
from montblanc.scraper import DayAvailability
from montblanc.trail_data import TMB_KM_FROM_START, get_km_from_start


class TestRefugeModel:
    """Tests for Refuge creation, equality, and hashing."""

    def test_create_minimal(self):
        r = Refuge(id="42", name="Test Refuge")
        assert r.id == "42"
        assert r.name == "Test Refuge"
        assert r.order is None
        assert r.km_from_start is None
        assert r.special is False

    def test_create_with_all_fields(self):
        r = Refuge(id="7", name="Refuge du Lac Blanc", order=3, km_from_start=160.0)
        assert r.order == 3
        assert r.km_from_start == 160.0

    def test_hash_equality(self):
        a = Refuge(id="1", name="A")
        b = Refuge(id="1", name="A")
        assert hash(a) == hash(b)
        assert a == b

    def test_hash_differs_by_id(self):
        a = Refuge(id="1", name="Same")
        b = Refuge(id="2", name="Same")
        assert hash(a) != hash(b)

    def test_hash_differs_by_name(self):
        a = Refuge(id="1", name="Alpha")
        b = Refuge(id="1", name="Beta")
        assert hash(a) != hash(b)

    def test_usable_in_set(self):
        r1 = Refuge(id="1", name="A")
        r2 = Refuge(id="1", name="A")
        r3 = Refuge(id="2", name="B")
        s = {r1, r2, r3}
        assert len(s) == 2

    def test_model_dump(self):
        r = Refuge(id="5", name="X", order=0, km_from_start=10.5)
        d = r.model_dump()
        assert d == {"id": "5", "name": "X", "order": 0, "km_from_start": 10.5, "special": False}

    def test_special_flag(self):
        r = Refuge(id="90001", name="Lac Blanc", special=True)
        assert r.special is True
        assert r.model_dump()["special"] is True


class TestTrailData:
    """Tests for the TMB distance lookup table."""

    def test_lac_blanc_present(self):
        assert "Refuge du Lac Blanc" in TMB_KM_FROM_START

    def test_lac_blanc_distance(self):
        assert TMB_KM_FROM_START["Refuge du Lac Blanc"] == 149.0

    def test_nant_borrant_present(self):
        assert "Refuge de Nant Borrant" in TMB_KM_FROM_START
        assert TMB_KM_FROM_START["Refuge de Nant Borrant"] == 20.0

    def test_distances_are_positive(self):
        for name, km in TMB_KM_FROM_START.items():
            assert km > 0, f"{name} has non-positive distance {km}"

    def test_distances_are_floats_or_ints(self):
        for name, km in TMB_KM_FROM_START.items():
            assert isinstance(km, (int, float)), f"{name} distance is {type(km)}"

    def test_has_reasonable_number_of_refuges(self):
        assert len(TMB_KM_FROM_START) >= 30

    def test_les_houches_is_near_start(self):
        assert TMB_KM_FROM_START["Chalet Les Méandres (ex Tupilak)"] < 5.0

    def test_distances_span_full_route(self):
        distances = list(TMB_KM_FROM_START.values())
        assert max(distances) >= 150, "Route should span at least 150 km"
        assert min(distances) < 5, "First refuge should be near the start"


class TestFuzzyMatching:
    """Tests for fuzzy refuge name matching via get_km_from_start."""

    def test_exact_match(self):
        assert get_km_from_start("Refuge de Nant Borrant") == 20.0

    def test_accent_variation(self):
        """A wrong accent (ê vs î) should still match."""
        assert get_km_from_start("Auberge Gête Bon Abri") == 115.0

    def test_case_insensitive(self):
        assert get_km_from_start("refuge de nant borrant") == 20.0

    def test_accent_stripped_match(self):
        """Fully stripped accents should still match."""
        assert get_km_from_start("Refuge de la Balme") == 22.0
        assert get_km_from_start("Hotel du Col de Fenetre") == 97.0

    def test_close_misspelling(self):
        """A minor misspelling should match via difflib."""
        assert get_km_from_start("Rifugio G. Berton") == 70.0

    def test_no_match_for_unrelated_name(self):
        assert get_km_from_start("Hotel Splendid Paris") is None

    def test_no_match_for_empty_string(self):
        assert get_km_from_start("") is None


class TestSpecialRefuge:
    """Tests for the SpecialRefuge abstract base class and registry."""

    def test_cannot_instantiate_abstract(self):
        """SpecialRefuge without check_availability cannot be instantiated."""
        import pytest

        class Incomplete(SpecialRefuge):
            refuge = Refuge(id="1", name="X", special=True)

        with pytest.raises(TypeError):
            Incomplete()

    def test_concrete_subclass(self):
        """A concrete SpecialRefuge can be instantiated and called."""

        class Dummy(SpecialRefuge):
            refuge = Refuge(id="99999", name="Dummy", special=True)

            def check_availability(self, start: date, end: date) -> list[DayAvailability]:
                return [
                    DayAvailability(date=start, places=5, status="available"),
                ]

        instance = Dummy()
        result = instance.check_availability(date(2026, 7, 1), date(2026, 7, 1))
        assert len(result) == 1
        assert result[0].places == 5


class TestFindViableStartsEmptyGroups:
    """Tests for find_viable_starts handling of empty groups (own reservations)."""

    def _make_avail_index(self, refuge_id, dates_places):
        """Build a minimal availability index for one refuge."""
        return {
            refuge_id: {
                d: DayAvailability(date=d, places=p, status="available")
                for d, p in dates_places.items()
            }
        }

    @patch("montblanc.logic._fetch_special_availability", return_value={})
    @patch("montblanc.logic._fetch_planning_data", return_value=[])
    @patch("montblanc.logic._build_availability_index")
    def test_empty_group_produces_skipped_night(self, mock_index, _mock_data, _mock_special):
        """An empty group produces a skipped night entry."""
        from montblanc.logic import find_viable_starts

        r = Refuge(id="1", name="Ref A")
        start = date(2026, 7, 1)
        avail = self._make_avail_index("1", {start: 5})
        mock_index.return_value = avail

        results = find_viable_starts(
            groups=[[r], []],
            start=start,
            end=start,
            min_places=1,
        )

        assert len(results) == 1
        nights = results[0]["nights"]
        assert len(nights) == 2
        assert nights[0]["refuge_name"] == "Ref A"
        assert nights[0].get("skipped") is not True
        assert nights[1]["skipped"] is True
        assert nights[1]["refuge_name"] == "Own reservation"
        assert nights[1]["date"] == (start + timedelta(days=1)).isoformat()

    @patch("montblanc.logic._fetch_special_availability", return_value={})
    @patch("montblanc.logic._fetch_planning_data", return_value=[])
    @patch("montblanc.logic._build_availability_index")
    def test_empty_group_between_filled_groups(self, mock_index, _mock_data, _mock_special):
        """An empty group between two filled groups works correctly."""
        from montblanc.logic import find_viable_starts

        r1 = Refuge(id="1", name="Ref A")
        r2 = Refuge(id="2", name="Ref B")
        start = date(2026, 7, 1)
        avail = {
            "1": {start: DayAvailability(date=start, places=3, status="available")},
            "2": {
                start + timedelta(days=2): DayAvailability(
                    date=start + timedelta(days=2), places=4, status="available"
                )
            },
        }
        mock_index.return_value = avail

        results = find_viable_starts(
            groups=[[r1], [], [r2]],
            start=start,
            end=start,
            min_places=1,
        )

        assert len(results) == 1
        nights = results[0]["nights"]
        assert len(nights) == 3
        assert nights[0]["refuge_name"] == "Ref A"
        assert nights[1]["skipped"] is True
        assert nights[2]["refuge_name"] == "Ref B"
