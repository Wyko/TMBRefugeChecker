"""FastAPI web application for TMB Refuge Availability Checker."""

import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from montblanc import logic

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
SELECTIONS_PATH = Path.home() / ".montblanc" / "web_selections.json"

app = FastAPI(title="TMB Refuge Checker")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve the main HTML page."""
    return (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/refuges")
def get_refuges():
    """Return all refuges in TMB route order.

    Returns:
        list[dict]: List of refuge dicts with id, name, and order fields.
    """
    refuges = logic.get_all_refuge_ids()
    return [r.model_dump() for r in refuges]


class CheckRequest(BaseModel):
    """Request body for the availability check endpoint."""

    groups: list[list[str]]
    start_date: date
    end_date: date
    min_places: int = 1


@app.post("/api/check")
def check_availability(req: CheckRequest):
    """Check availability across grouped refuges and return viable start dates.

    Args:
        req (CheckRequest): The check request with groups, date range, and
            minimum places.

    Returns:
        dict: A dict with ``results`` key containing viable itineraries.
    """
    all_refuges = {r.id: r for r in logic.get_all_refuge_ids()}

    groups = []
    for group_ids in req.groups:
        group = []
        for rid in group_ids:
            refuge = all_refuges.get(rid)
            if refuge:
                group.append(refuge)
        groups.append(group)

    results = logic.find_viable_starts(
        groups=groups,
        start=req.start_date,
        end=req.end_date,
        min_places=req.min_places,
    )

    return {"results": results}


class SaveSelectionsRequest(BaseModel):
    """Request body for saving the current night selections."""

    groups: list[list[dict]]
    settings: dict | None = None


@app.post("/api/selections/save")
def save_selections(req: SaveSelectionsRequest):
    """Save the current night group selections to disk.

    Args:
        req (SaveSelectionsRequest): The groups and optional settings to save.

    Returns:
        dict: Confirmation with ``ok`` key.
    """
    payload = {"groups": req.groups}
    if req.settings:
        payload["settings"] = req.settings
    SELECTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SELECTIONS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True}


@app.get("/api/selections/load")
def load_selections():
    """Load previously saved night group selections from disk.

    Returns:
        dict: The saved groups and settings, or empty groups if no save exists.
    """
    if not SELECTIONS_PATH.exists():
        return {"groups": [], "settings": None}
    data = json.loads(SELECTIONS_PATH.read_text(encoding="utf-8"))
    return data


@app.post("/api/refresh")
def refresh_cache():
    """Force-clear all caches (in-memory and disk) so the next request scrapes fresh data.

    Returns:
        dict: Confirmation with ``ok`` key.
    """
    logic.force_refresh_cache()
    return {"ok": True}
