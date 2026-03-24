# Copilot Instructions

## Project Overview

TMB Refuge Checker is a tool for checking refuge (mountain hut) availability
along the Tour du Mont Blanc hiking route (~170 km). It scrapes availability
data from montourdumontblanc.com and presents it via a CLI and a web UI.

### Entry Points

- **CLI** (`montblanc/main.py`): Typer app with commands `list`, `check`, `web`,
  and the `plan` subcommand group (`plan check`, `plan day`, `plan show`).
- **Web UI** (`montblanc/web/app.py`): FastAPI app serving a drag-and-drop
  itinerary planner at `/`, with API endpoints `GET /api/refuges` and
  `POST /api/check`.

### Core Modules

| Module | Purpose |
|---|---|
| `montblanc/scraper.py` | Scrapes the montourdumontblanc.com planning page. Parses calendar HTML into `RefugeAvailability` / `DayAvailability` dataclasses. |
| `montblanc/logic.py` | Business logic: caching, availability indexing, `find_viable_starts()` algorithm, `Plan` class for multi-day itineraries. |
| `montblanc/trail_data.py` | Static lookup table mapping refuge names to cumulative km from Les Houches. |
| `montblanc/refuges/__init__.py` | `Refuge` Pydantic model, `SpecialRefuge` ABC, and auto-discovery registry. |
| `montblanc/types.py` | Typer CLI argument/option type definitions. |

### Refuge Architecture

There are two categories of refuges:

#### Standard Refuges (montourdumontblanc.com)

The majority of refuges are listed on montourdumontblanc.com. Their availability
is fetched in a single HTTP call by `scraper.scrape_planning()`, cached for 5
minutes, and indexed by numeric ID. Each refuge gets a `Refuge` object with
`special=False`.

#### Special Refuges (independent booking systems)

Some refuges (e.g. Refuge du Lac Blanc) are not part of montourdumontblanc.com
and must be queried independently. These are implemented as subclasses of
`SpecialRefuge` in modules under `montblanc/refuges/`:

```
montblanc/refuges/
    __init__.py          # Refuge model, SpecialRefuge ABC, registry
    du_lac_blanc.py      # Lac Blanc special refuge
```

To add a new special refuge:

1. Create a module in `montblanc/refuges/` (e.g. `my_refuge.py`).
2. Subclass `SpecialRefuge`, set the `refuge` class attribute with a `Refuge`
   instance (`special=True`, unique ID in the 90000+ range).
3. Implement `check_availability(start, end) -> list[DayAvailability]`.
4. Export a module-level `special_refuge` instance.

The registry (`get_special_refuges()`) auto-discovers these modules at runtime.
Special refuge availability is merged into the main index by `logic.py` so they
work seamlessly with `find_viable_starts()` and the web UI.

### Key Data Flow

```
scrape_planning()  ──→  list[RefugeAvailability]  ──→  _build_availability_index()
                                                            ↓
SpecialRefuge.check_availability()  ──→  _fetch_special_availability()
                                                            ↓
                                                   merged avail_index
                                                            ↓
                                                   find_viable_starts()
                                                            ↓
                                                   viable itineraries
```

### Availability Statuses

The scraper maps CSS classes to status strings:

| CSS class | Status | Meaning |
|---|---|---|
| `bg-primary` | `available` | Bookable, places shown |
| `bg-warning` | `last_seats` | Bookable, few places left |
| `bg-danger` | `full` | No places available |
| `bg-black` | `not_bookable` | Not available for online booking |
| `bg-light` | `not_open` | Booking not yet open |
| (other) | `closed` | Closed for the season |

## Caching

All caching should use disk-based storage (e.g. `_read_disk_cache` /
`_write_disk_cache` in `logic.py`) unless there is a specific reason for
in-memory caching to be more appropriate.

## Docstrings

All major functions and methods must include Google-style docstrings with:
- A summary line
- An `Args:` section listing each parameter with its type and description
- A `Returns:` section describing the return value and type
