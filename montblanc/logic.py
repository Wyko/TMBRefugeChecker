"""Check the availability of refuges on the Tour du Mont Blanc.

Uses the scraper module to fetch all availability data from
montourdumontblanc.com in a single HTTP call.  Results are cached in
memory and refreshed every ``REFRESH_TIMEOUT`` seconds.
"""

import json
import logging
import os
import pickle
import time
import winsound
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

import times
from cachetools.func import ttl_cache
from tqdm import tqdm

from montblanc.refuges import Refuge, SpecialRefuge, get_special_refuges
from montblanc.scraper import DayAvailability, RefugeAvailability, scrape_planning
from montblanc.trail_data import get_km_from_start

logging.basicConfig(level=logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".montblanc" / "cache"

REFRESH_TIMEOUT = times.FIVE_MINUTES


def _read_disk_cache(name: str, max_age: float = REFRESH_TIMEOUT) -> object | None:
    """Read a pickled cache file if it exists and is fresh enough.

    Args:
        name (str): Cache file base name (without extension).
        max_age (float): Maximum age in seconds before the cache is stale.

    Returns:
        object | None: The cached object, or None if missing/stale.
    """
    path = CACHE_DIR / f"{name}.pkl"
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > max_age:
        return None
    try:
        return pickle.loads(path.read_bytes())
    except Exception:
        logger.warning("Failed to read disk cache %s", path, exc_info=True)
        return None


def _write_disk_cache(name: str, data: object) -> None:
    """Write an object to the disk cache as a pickle file.

    Args:
        name (str): Cache file base name (without extension).
        data (object): The object to cache.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{name}.pkl"
    try:
        path.write_bytes(pickle.dumps(data))
    except Exception:
        logger.warning("Failed to write disk cache %s", path, exc_info=True)


@ttl_cache(maxsize=1, ttl=REFRESH_TIMEOUT)
def _fetch_planning_data() -> list[RefugeAvailability]:
    """Fetch and cache all refuge availability from the planning page.

    Results are cached in memory for ``REFRESH_TIMEOUT`` seconds and
    persisted to disk so restarts don't require a fresh scrape.

    Returns:
        list[RefugeAvailability]: All refuges with their availability calendars.
    """
    cached = _read_disk_cache("planning_data")
    if cached is not None:
        return cached
    data = scrape_planning()
    _write_disk_cache("planning_data", data)
    return data


def _build_availability_index(
    data: list[RefugeAvailability],
) -> dict[str, dict[date, DayAvailability]]:
    """Build a lookup from refuge numeric_id to date to DayAvailability.

    Args:
        data (list[RefugeAvailability]): Scraped refuge data.

    Returns:
        dict[str, dict[date, DayAvailability]]: Nested mapping of refuge ID
            to date to availability info.
    """
    index: dict[str, dict[date, DayAvailability]] = {}
    for r in data:
        index[r.numeric_id] = {d.date: d for d in r.days}
    return index


def _apply_trail_distances(refuges: list[Refuge]) -> None:
    """Set ``km_from_start`` on each refuge using the trail-distance lookup.

    Uses fuzzy matching to handle minor name variations (accents,
    spelling differences) between the scraper and the distance table.

    Args:
        refuges (list[Refuge]): The refuges to update in-place.
    """
    for r in refuges:
        km = get_km_from_start(r.name)
        if km is not None:
            r.km_from_start = km


def _fetch_special_availability(
    start: date, end: date,
) -> dict[str, dict[date, DayAvailability]]:
    """Fetch availability from all special refuges and return an index.

    Results are cached to disk for ``REFRESH_TIMEOUT`` seconds.

    Args:
        start (date): The first date to check (inclusive).
        end (date): The last date to check (inclusive).

    Returns:
        dict[str, dict[date, DayAvailability]]: Mapping of refuge ID to
            date to availability, same shape as ``_build_availability_index``.
    """
    cache_key = f"special_{start.isoformat()}_{end.isoformat()}"
    cached = _read_disk_cache(cache_key)
    if cached is not None:
        return cached

    index: dict[str, dict[date, DayAvailability]] = {}
    for special in get_special_refuges():
        try:
            days = special.check_availability(start, end)
        except Exception:
            logger.warning(
                "Failed to fetch availability for special refuge %s",
                special.refuge.name,
                exc_info=True,
            )
            continue
        index[special.refuge.id] = {d.date: d for d in days}

    _write_disk_cache(cache_key, index)
    return index


def force_refresh_cache() -> None:
    """Clear both in-memory and disk caches, forcing a fresh scrape.

    Removes the in-memory TTL cache and all disk cache files.
    """
    _fetch_planning_data.cache_clear()
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.pkl"):
            f.unlink(missing_ok=True)


def get_all_refuge_ids(force_refresh: bool = False) -> list[Refuge]:
    """Get all refuges from montourdumontblanc.com.

    Results come from the scraper and are cached in memory.
    Pass ``force_refresh=True`` to bypass the cache.

    Args:
        force_refresh (bool): If True, clear the cache and re-scrape.
            Defaults to False.

    Returns:
        list[Refuge]: Refuges sorted by TMB route order.
    """
    if force_refresh:
        _fetch_planning_data.cache_clear()

    data = _fetch_planning_data()
    refuges = [
        Refuge(id=r.numeric_id, name=r.name, order=idx)
        for idx, r in enumerate(data)
    ]

    # Append special refuges (not on montourdumontblanc.com)
    existing_ids = {r.id for r in refuges}
    for special in get_special_refuges():
        if special.refuge.id not in existing_ids:
            refuges.append(special.refuge.model_copy())

    _apply_trail_distances(refuges)
    refuges.sort(key=lambda r: (r.order is None, r.order, r.name))
    return refuges


def _refuge_by_name(name: str) -> Refuge:
    """Look up a Refuge by name (exact match first, then substring).

    Args:
        name (str): Exact or partial refuge name.

    Returns:
        Refuge: The matched refuge.

    Raises:
        ValueError: If no match is found.
    """
    for refuge in get_all_refuge_ids():
        if refuge.name == name:
            return refuge
    for refuge in get_all_refuge_ids():
        if name.lower() in refuge.name.lower():
            return refuge
    raise ValueError(f"Could not find refuge with name {name}")


def _refuge_by_id(refuge_id: int | str) -> Refuge:
    """Look up a Refuge by its numeric ID.

    Args:
        refuge_id (int | str): The refuge ID.

    Returns:
        Refuge: The matched refuge, or a placeholder if not found.
    """
    rid = str(refuge_id)
    for refuge in get_all_refuge_ids():
        if refuge.id == rid:
            return refuge
    return Refuge(id=rid, name=f"Unknown Refuge ({rid})")


def convert_refuge(refuge: int | str | dict | Refuge) -> Refuge:
    """Convert a refuge given as int, str, dict, or Refuge to a Refuge object.

    Args:
        refuge (int | str | dict | Refuge): Refuge identifier in various forms.

    Returns:
        Refuge: The resolved Refuge object.

    Raises:
        ValueError: If conversion fails.
    """
    if isinstance(refuge, Refuge):
        return refuge
    if isinstance(refuge, dict):
        return Refuge.model_validate(refuge)
    try:
        return _refuge_by_id(int(refuge))
    except (ValueError, TypeError):
        pass
    if isinstance(refuge, str):
        return _refuge_by_name(refuge)
    raise ValueError(f"Could not convert {refuge} to a Refuge object.")


def _get_availability(refuge_id: str, d: date) -> DayAvailability | None:
    """Look up availability for a refuge on a specific date.

    Args:
        refuge_id (str): The numeric refuge ID.
        d (date): The date to check.

    Returns:
        DayAvailability | None: Availability info, or None if not found.
    """
    data = _fetch_planning_data()
    index = _build_availability_index(data)
    return index.get(refuge_id, {}).get(d)


def _alert_on_availability(
    d: date, refuge: Refuge, min_places: int = 3, name_width: int = 30,
) -> bool:
    """Print availability status for a refuge on a given date.

    Args:
        d (date): The date to check.
        refuge (Refuge): The refuge to check.
        min_places (int): Minimum places to trigger a positive alert.
            Defaults to 3.
        name_width (int): Column width for the refuge name. Defaults to 30.

    Returns:
        bool: True if the refuge has enough available places.
    """
    avail = _get_availability(refuge.id, d)
    label = refuge.name.rjust(name_width)
    date_str = d.strftime(r"%A, %b %d, %Y")

    if avail is None:
        print(f"    {label}: No data for {date_str}")
        return False

    if avail.status in ("closed", "full"):
        print(f"    {label}: Closed/full on {date_str}")
        return False

    if avail.status == "not_bookable":
        print(f"    {label}: Not bookable online")
        return False

    if avail.status == "not_open":
        print(f"    {label}: Booking not yet open")
        return False

    if avail.status in ("available", "last_seats"):
        places = avail.places or 0
        if places >= min_places:
            print(f"!!! {label}: {places} places on {date_str} !!!")
            return True
        print(f"    {label}: Only {places} places on {date_str}")
        return False

    print(f"    {label}: {avail.status} on {date_str}")
    return False


def _make_noise():
    """Make a noise to alert the user."""
    for _ in range(5):
        for _ in range(3):
            for _ in range(4):
                winsound.Beep(440, 100)
                time.sleep(0.05)
            time.sleep(0.5)
        time.sleep(1)


def _best_refuge_for_night(
    group: list[Refuge],
    night_date: date,
    avail_index: dict[str, dict[date, DayAvailability]],
    min_places: int,
) -> dict | None:
    """Find the best available refuge in a group for a specific night.

    Args:
        group (list[Refuge]): Candidate refuges for this night.
        night_date (date): The date of the night.
        avail_index (dict[str, dict[date, DayAvailability]]): Availability
            index from ``_build_availability_index``.
        min_places (int): Minimum places required.

    Returns:
        dict | None: Info dict with date, refuge_name, refuge_id, places,
            and reservation_url if a suitable refuge is found, otherwise None.
    """
    best = None
    best_avail = None
    for refuge in group:
        day_avail = avail_index.get(refuge.id, {}).get(night_date)
        if not day_avail or day_avail.status not in ("available", "last_seats"):
            continue
        places = day_avail.places or 0
        if places < min_places:
            continue
        if best is None or places > best["places"]:
            best = {
                "date": night_date.isoformat(),
                "refuge_name": refuge.name,
                "refuge_id": refuge.id,
                "places": places,
            }
            best_avail = day_avail
    if best and best_avail and best_avail.reservation_url:
        best["reservation_url"] = best_avail.reservation_url
    return best


def find_viable_starts(
    groups: list[list[Refuge]],
    start: date,
    end: date,
    min_places: int = 1,
) -> list[dict]:
    """Find starting dates where consecutive nights can be booked across refuge groups.

    For each candidate start date, checks whether at least one refuge in each
    group has availability on consecutive days (group 0 on day 0, group 1 on
    day 1, etc.).

    Args:
        groups (list[list[Refuge]]): Ordered list of refuge groups. Each group
            is a list of alternative refuges for that night.
        start (date): The earliest start date to consider (inclusive).
        end (date): The latest start date to consider (inclusive).
        min_places (int): Minimum available places required. Defaults to 1.

    Returns:
        list[dict]: A list of viable itineraries, each with keys ``start_date``
            (str) and ``nights`` (list of dicts with ``date``, ``refuge_name``,
            ``refuge_id``, ``places``).
    """
    num_nights = len(groups)
    if num_nights == 0:
        return []

    data = _fetch_planning_data()
    avail_index = _build_availability_index(data)

    # Merge special refuge availability into the index
    special_index = _fetch_special_availability(start, end)
    avail_index.update(special_index)

    results: list[dict] = []
    candidate = start
    while candidate <= end:
        nights: list[dict] = []
        viable = True

        for night_idx, group in enumerate(groups):
            night_date = candidate + timedelta(days=night_idx)

            if not group:
                # Empty group = user has their own reservation for this night
                nights.append({
                    "date": night_date.isoformat(),
                    "refuge_name": "Own reservation",
                    "refuge_id": None,
                    "places": None,
                    "skipped": True,
                })
                continue

            best = _best_refuge_for_night(group, night_date, avail_index, min_places)

            if best is None:
                viable = False
                break
            nights.append(best)

        if viable:
            results.append({"start_date": candidate.isoformat(), "nights": nights})

        candidate += timedelta(days=1)

    return results


def check_refuges(
    refuges: list[int | str | Refuge],
    date: datetime,
    min_places: int = 3,
    silent: bool = False,
):
    """Check the availability of a list of refuges on a given date.

    Runs in an infinite loop, re-checking every ``REFRESH_TIMEOUT`` seconds.

    Args:
        refuges (list[int | str | Refuge]): A list of refuge IDs, names, or
            Refuge objects to check.
        date (datetime): The date to check.
        min_places (int): Minimum places for an alert. Defaults to 3.
        silent (bool): If True, suppress noise alerts. Defaults to False.
    """
    ref_objs: List[Refuge] = [convert_refuge(r) for r in refuges]
    check_date = date.date() if isinstance(date, datetime) else date
    name_width = max(len(r.name) for r in ref_objs) if ref_objs else 30

    while True:
        os.system("cls||clear")
        found = False
        for refuge in ref_objs:
            if _alert_on_availability(check_date, refuge, min_places, name_width):
                found = True
        if found and not silent:
            _make_noise()
        sleep_with_waiting_bar()
        _fetch_planning_data.cache_clear()


def sleep_with_waiting_bar(timeout: int = REFRESH_TIMEOUT):
    """Display a progress bar while waiting for the next refresh cycle.

    Args:
        timeout (int): The number of seconds to wait. Defaults to
            ``REFRESH_TIMEOUT``.
    """
    print("")
    for _ in tqdm(
        range(timeout * 2),
        leave=False,
        ncols=80,
        bar_format="Waiting to check availability: {remaining} {bar}",
    ):
        time.sleep(0.5)


class Plan:
    """A multi-day hiking plan with refuges to check for availability."""

    def __init__(self, path: Optional[str] = None):
        """Initialise a Plan, optionally loading from a JSON file.

        Args:
            path (Optional[str]): Path to a ``.json`` plan file. If ``None``,
                uses the default plan at ``~/.montblanc/default_plan.json``.
        """
        if path:
            if not path.endswith(".json"):
                raise ValueError(
                    "Plan file must be a JSON file. The path should end with '.json'. For "
                    "example, 'C:/Users/Me/.montblanc/plan.json'"
                )
            resolved = Path(path)
            if not resolved.exists():
                raise FileNotFoundError(f"Could not find plan at {resolved}")

        else:
            resolved = Path.home() / ".montblanc" / "default_plan.json"

        self.days: dict[datetime, set[Refuge]] = defaultdict(set)
        self.path: Path = resolved

        self.load(self.path)

    def check(self, min_places: int = 3, silent: bool = False):
        """Check availability for all refuges in the plan.

        Runs in an infinite loop, re-checking every ``REFRESH_TIMEOUT`` seconds.

        Args:
            min_places (int): Minimum places to trigger an alert. Defaults to 3.
            silent (bool): If True, suppress noise alerts. Defaults to False.
        """
        if not self.days:
            raise ValueError("No days have been added to the plan. Use `add_day` to add days to the plan.")

        while True:
            os.system("cls||clear")

            all_refuges = [r for day_refuges in self.days.values() for r in day_refuges]
            name_width = max(len(r.name) for r in all_refuges) if all_refuges else 30

            places_found = False
            for day, refuges in self.days.items():
                check_date = day.date() if isinstance(day, datetime) else day
                for refuge in refuges:
                    if _alert_on_availability(check_date, refuge, min_places, name_width):
                        places_found = True

            if places_found and not silent:
                _make_noise()

            sleep_with_waiting_bar()
            _fetch_planning_data.cache_clear()

    def add_day(
        self,
        date: datetime,
        refuges: list[int | str | Refuge],
        print_refuges: bool = False,
    ):
        """Add a day to the plan. If the day already exists, the refuges will replace the existing day.

        Args:
            date (datetime): The date of the day.
            refuges (list[int | str | Refuge]): A list of refuges to stay at on
                the given date.
            print_refuges (bool): Print the added refuges. Defaults to False.
        """
        if not refuges:
            self.days.pop(date, None)
            if print_refuges:
                print(f"Cleared {date.strftime(r'%A, %b %d, %Y')}")
            self.save()
            return

        c_refuges = [convert_refuge(refuge) for refuge in refuges]
        self.days[date] = set(sorted(c_refuges, key=lambda x: x.name))
        self.days = dict(sorted(self.days.items()))

        if print_refuges:
            print(f"Added {date.strftime(r'%A, %b %d, %Y')}:")
            for refuge in c_refuges:
                print(f"  - {refuge.name}")

        self.save()

    def save(self):
        """Save the plan to a file."""
        payload = {
            "days": [
                {
                    "date": day.strftime(r"%Y-%m-%d"),
                    "refuges": [r.model_dump() for r in sorted(refuges, key=lambda x: x.name)],
                }
                for day, refuges in self.days.items()
            ]
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w") as f:
            json.dump(payload, f, indent=4)

    def load(self, path: Path):
        """Load a plan from a file.

        Args:
            path (Path): The path to load the plan from.
        """
        if not path.exists():
            self.days = defaultdict(set)
            return

        with open(path, "r") as f:
            payload = json.load(f)

        for day in payload["days"]:
            refuges = []
            for cached_refuge in day["refuges"]:
                for refuge in get_all_refuge_ids():
                    if refuge.id == cached_refuge["id"] or refuge.name == cached_refuge["name"]:
                        refuges.append(refuge)
                        break

            self.add_day(datetime.strptime(day["date"], r"%Y-%m-%d"), refuges)
