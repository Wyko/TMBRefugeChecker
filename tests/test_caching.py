"""Tests for disk caching and web API save/load/refresh endpoints."""

import json
import pickle
import time
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from montblanc.logic import (
    CACHE_DIR,
    _read_disk_cache,
    _write_disk_cache,
    force_refresh_cache,
)
from montblanc.scraper import DayAvailability


class TestDiskCache:
    """Tests for _read_disk_cache / _write_disk_cache helpers."""

    def test_write_and_read(self, tmp_path):
        with patch("montblanc.logic.CACHE_DIR", tmp_path):
            _write_disk_cache("test_item", {"hello": "world"})
            result = _read_disk_cache("test_item")
        assert result == {"hello": "world"}

    def test_read_missing_returns_none(self, tmp_path):
        with patch("montblanc.logic.CACHE_DIR", tmp_path):
            assert _read_disk_cache("nonexistent") is None

    def test_read_stale_returns_none(self, tmp_path):
        with patch("montblanc.logic.CACHE_DIR", tmp_path):
            _write_disk_cache("old_item", [1, 2, 3])
            # Backdate the file
            cache_file = tmp_path / "old_item.pkl"
            old_time = time.time() - 600
            import os
            os.utime(cache_file, (old_time, old_time))
            assert _read_disk_cache("old_item", max_age=300) is None

    def test_read_fresh_returns_data(self, tmp_path):
        with patch("montblanc.logic.CACHE_DIR", tmp_path):
            _write_disk_cache("fresh_item", "data")
            assert _read_disk_cache("fresh_item", max_age=300) == "data"

    def test_write_creates_directory(self, tmp_path):
        nested = tmp_path / "sub" / "dir"
        with patch("montblanc.logic.CACHE_DIR", nested):
            _write_disk_cache("nested_item", 42)
            assert (nested / "nested_item.pkl").exists()


class TestForceRefreshCache:
    """Tests for force_refresh_cache()."""

    def test_clears_disk_cache(self, tmp_path):
        with patch("montblanc.logic.CACHE_DIR", tmp_path):
            _write_disk_cache("a", 1)
            _write_disk_cache("b", 2)
            assert len(list(tmp_path.glob("*.pkl"))) == 2
            force_refresh_cache()
            assert len(list(tmp_path.glob("*.pkl"))) == 0

    def test_clears_memory_cache(self, tmp_path):
        from montblanc.logic import _fetch_planning_data
        with patch("montblanc.logic.CACHE_DIR", tmp_path):
            _fetch_planning_data.cache_clear()  # ensure clean state
            force_refresh_cache()  # should not raise


class TestWebEndpoints:
    """Tests for save/load/refresh API endpoints."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from montblanc.web.app import app
        return TestClient(app)

    def test_save_and_load_selections(self, client, tmp_path):
        save_path = tmp_path / "selections.json"
        with patch("montblanc.web.app.SELECTIONS_PATH", save_path):
            payload = {
                "groups": [[{"id": "1", "name": "Ref A"}], []],
                "settings": {"dailyKm": "20"},
            }
            res = client.post("/api/selections/save", json=payload)
            assert res.status_code == 200
            assert res.json()["ok"] is True
            assert save_path.exists()

            res = client.get("/api/selections/load")
            assert res.status_code == 200
            data = res.json()
            assert len(data["groups"]) == 2
            assert data["groups"][0][0]["name"] == "Ref A"
            assert data["settings"]["dailyKm"] == "20"

    def test_load_empty(self, client, tmp_path):
        save_path = tmp_path / "no_such_file.json"
        with patch("montblanc.web.app.SELECTIONS_PATH", save_path):
            res = client.get("/api/selections/load")
            assert res.status_code == 200
            assert res.json() == {"groups": [], "settings": None}

    def test_refresh_endpoint(self, client, tmp_path):
        with patch("montblanc.logic.CACHE_DIR", tmp_path):
            _write_disk_cache("planning_data", "stale")
            res = client.post("/api/refresh")
            assert res.status_code == 200
            assert res.json()["ok"] is True
            assert len(list(tmp_path.glob("*.pkl"))) == 0
