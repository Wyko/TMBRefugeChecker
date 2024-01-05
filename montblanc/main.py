"""A script to check the availability of refuges on the Tour du Mont Blanc.

The script uses a cache to avoid querying the same date multiple times. The cache is refreshed every
`REFRESH_TIMEOUT` seconds. The cache is stored in memory, so it will be lost when the program exits.

Usage:
    >> check_refuges(
        [
            LES_CHAMBRES_DU_SOLEIL,
            AUBERGE_REFUGE_DE_LA_NOVA,
        ],
        datetime(2024, 9, 11),
    )
    Waiting to check availability: 59 [##############################################] 100%
    Waiting to check availability: 59 [##############################################] 100%
    Waiting to check availability: 59 [##############################################] 100%
    Refuge 32367 has 4 places left on Saturday, Sep 11, 2024!
"""

import json
import logging
import os
import re
import time
import winsound
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import httpx
import pydantic
import times
import typer
from bs4 import BeautifulSoup
from cachetools.func import ttl_cache
from tqdm import tqdm
from typing_extensions import Annotated

logging.basicConfig(level=logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class Refuge(pydantic.BaseModel):
    id: int
    name: str

    def __hash__(self) -> int:
        return hash((self.id, self.name))


class Montblanc:
    """A class for querying the availability of refuges on the Tour du Mont Blanc.

    The class uses a cache to avoid querying the same date multiple times. The cache is refreshed every
    `REFRESH_TIMEOUT` seconds. The cache is stored in memory, so it will be lost when the program exits.

    The Refuge ID for any given refuge can be found by inspecting the URL of the refuge's page on the
    Mont Blanc website. For example, the refuge ID for the Auberge-Refuge de la Nova is 32367, and the
    URL for the refuge's page is https://www.montourdumontblanc.com/fr/il4-refuge_i32378-auberge-la-boerne.aspx.
    The refuge ID is the number after `refuge_i` in the URL.

    Attributes:
        REFRESH_TIMEOUT (int): The number of seconds to wait before refreshing the cache. Defaults to 60.

    Usage:
        >> mb = Montblanc()
        >> mb.alert_on_availability(datetime(2024, 9, 11), 32367, 3)
        Refuge 32367 has 4 places left on Saturday, Sep 11, 2024
    """

    REFRESH_TIMEOUT = times.FIVE_MINUTES

    def __init__(self):
        self.client = httpx.Client()
        self.availability = {}
        self.get_refuge_names()

    @ttl_cache(maxsize=100, ttl=REFRESH_TIMEOUT)
    def _query_status(self, date: datetime, refuge_id: int) -> dict:
        """Query the status of a refuge on a given date.

        Do not call this method directly. Instead, use `get_availability` for the caching.

        Args:
            date (datetime): The date to query
            refuge_id (int, optional): The ID of the refuge to query. Defaults to 32367.

        Returns:
            dict: A dictionary containing the number of places available at the refuge on the given date,
                whether the refuge is closed on the given date, and the time the status was retrieved.
                Example::

            {
                "places": 4,
                "closed": False,
                "retrieved": datetime(2021, 8, 1, 12, 0, 0),
            }
        """
        logger.debug(f"Querying {refuge_id} on {date.strftime(r'%A, %b %d, %Y')}")
        datestr = date.strftime(r"%Y-%m-%d")

        r = self.client.get(
            "https://etape-rest.for-system.com/index.aspx/index.aspx",
            params={"ref": "json-planning-refuge", "q": f"{refuge_id},{datestr}"},
        )
        r.raise_for_status()
        response = json.loads(r.text.strip("()[]")).get("planning", list())

        for item in response:
            d = date + timedelta(days=item["d"])
            self.availability[d] = {
                "places": item["s"],
                "closed": item["f"] == 1,
                "retrieved": datetime.now(),
            }

        return self.availability[date]

    def get_availability(self, date: datetime, refuge_id: int) -> dict:
        """Get the availability of a refuge on a given date.

        This method will return the cached availability if it is available and not stale.

        Args:
            date (datetime): The date to query
            refuge_id (int): The ID of the refuge to query

        Returns:
            dict: A dictionary containing the number of places available at the refuge on the given date,
                whether the refuge is closed on the given date, and the time the status was retrieved.
                Example::

            {
                "places": 4,
                "closed": False,
                "retrieved": datetime(2021, 8, 1, 12, 0, 0),
            }
        """
        if (
            date in self.availability
            and self.availability[date]["retrieved"]
            > datetime.now() - timedelta(seconds=self.REFRESH_TIMEOUT)
            and True
        ):
            return self.availability[date]

        return self._query_status(date, refuge_id)

    @ttl_cache(maxsize=1, ttl=times.ONE_DAY)  # 1 day
    def get_regions(self) -> list[dict[str, str]]:
        """Get a list of regions and the IDs of refuges in them."""
        r = self.client.get(
            r"https://jsonp.open-system.fr/jsonp.aspx?px=http://www.montourdumontblanc.com/uk/json-listezonesgeo.xml",
        )
        r.raise_for_status()
        response: list[dict[str, str]] = json.loads(r.text.strip("()[]\r\n ;"))["ListeId"]
        for loc in response:
            loc["Nom"] = loc["Nom"].replace("&nbsp;", "'").strip("- '")
            loc["Id"] = loc["Id"].strip().split(",")
            loc["Id"] = [int(i) for i in loc["Id"]]

        return response

    def alert_on_availability(
        self, date: datetime, refuge: Refuge, min_places: int = 3, noise: bool = True
    ) -> bool:
        """Print an alert if there are more than `min_places` places available at `refuge_id` on `date`"""
        availability = self.get_availability(date, refuge.id)
        if availability["closed"]:
            print(f"Refuge {refuge.name} is closed on {date.strftime(r'%A, %b %d, %Y')}")
            return False

        if availability["places"] > min_places:
            print(
                f"!!! Refuge {refuge.name} has {availability['places']} places left on {date.strftime(r'%A, %b %d, %Y')} !!!"
            )
            if noise:
                self._make_noise()
            return True

        print(f"{refuge.name} has {availability['places']} places left on {date.strftime(r'%A, %b %d, %Y')}")
        return False

    def _make_noise(self):
        """Make a noise to alert the user."""
        for _ in range(5):
            for _ in range(3):
                for _ in range(4):
                    winsound.Beep(440, 100)
                    time.sleep(0.05)
                time.sleep(0.5)
            time.sleep(1)

    @ttl_cache(maxsize=1, ttl=times.ONE_DAY)
    def get_refuge_names(self) -> list[Refuge]:
        """Get the names and IDs of all refuges on montourdumontblanc.com.

        This is cached for 1 day.

        Returns:
            list[Refuge]: A list of refuges
        """
        r = httpx.get("https://www.montourdumontblanc.com/uk/index.aspx")
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        refuges = []

        refuge_tabs = soup.find("div", {"id": "tabsrefuges"})
        listings = refuge_tabs.find_all("div", {"class": "refuge"})
        for refuge in listings:
            href = refuge.find("a").get("href")
            _id = re.search(r"refuge_i(\d+)", href)
            if not _id:
                continue
            _id = _id.group(1)

            name = refuge.find("div", {"class": "bloccontenurefuge"}).h3.text
            logger.debug(f"Refuge {name} ID is {_id}")
            refuges.append(Refuge(id=_id, name=name))

        logger.info(f"Found {len(refuges)} refuges")
        refuges.sort(key=lambda x: x.name)
        return refuges

    def refuge_by_name(self, refuge_name: str) -> Refuge:
        """Lookup a Refuge by its name.

        Args:
            refuge_name (str): The name of the refuge to look up

        Returns:
            Refuge: A refuge object

        Raises:
            ValueError: If the refuge cannot be found
        """
        for refuge in self.get_refuge_names():
            if refuge.name == refuge_name:
                return refuge

        # Fuzzier search
        for refuge in self.get_refuge_names():
            if refuge_name.lower() in refuge.name.lower():
                return refuge

        raise ValueError(f"Could not find refuge with name {refuge_name}")

    def refuge_by_id(self, refuge_id: int) -> Refuge:
        """Lookup a Refuge by its ID.

        Args:
            refuge_id (int): The ID of the refuge to look up

        Returns:
            Refuge: A refuge object. If the refuge cannot be found, a refuge object with the ID and name
                "Unknown Refuge (refuge_id)" will be returned.
        """
        for refuge in self.get_refuge_names():
            if refuge.id == refuge_id:
                return refuge

        return Refuge(id=refuge_id, name=f"Unknown Refuge ({refuge_id})")


mb = Montblanc()


def check_refuges(refuges: list[int | str | Refuge], date: datetime, min_places: int = 3):
    """Check the availability of a list of refuges on a given date.

    The function will print an alert if there are more than `min_places` places available at any of the
    refuges on the given date. It will also print an alert if any of the refuges are closed on the given date.

    Args:
        refuges (list[int | str | Refuge]): A list of refuge IDs or names to check
        date (datetime): The date to check
        min_places (int, optional): The minimum number of places available to trigger an alert. Defaults to 3.
    """

    # Find the refuge objects corresponding to the given refuges
    ref_objs: List[Refuge] = []
    for refuge in refuges:
        ref_objs.append(convert_refuge(refuge))

    while True:
        # Clear the terminal
        os.system("cls||clear")

        # Check the availability of each refuge
        for refuge in ref_objs:
            mb.alert_on_availability(date, refuge, min_places)

        # Wait for the refresh timeout
        sleep_with_waiting_bar()


def convert_refuge(refuge: int | str | dict | Refuge):
    """Convert a refuge (given as an Int, Str, dict or Refuge) to a Refuge object."""
    try:
        refuge = int(refuge)
    except (ValueError, TypeError):
        pass

    if isinstance(refuge, int):
        return mb.refuge_by_id(refuge)
    elif isinstance(refuge, Refuge):
        return refuge
    elif isinstance(refuge, dict):
        return Refuge.model_validate(refuge)
    else:
        return mb.refuge_by_name(refuge)


def check_region(region: str, date: datetime, min_places: int = 3):
    """Check the availability of all of refuges in a given region on a given date.

    The function will print an alert if there are more than `min_places` places available at any of the
    refuges on the given date. It will also print an alert if any of the refuges are closed on the given date.

    Args:
        region (str): A region to check
        date (datetime): The date to check
        min_places (int, optional): The minimum number of places available to trigger an alert. Defaults to 3.
    """

    while True:
        # Clear the terminal
        os.system("cls||clear")

        # Check the availability of each refuge
        for refuge in mb.get_regions():
            if region in refuge["Nom"]:
                for refuge_id in refuge["Id"]:
                    mb.alert_on_availability(date, mb.refuge_by_id(refuge_id), min_places)

        # Wait for the refresh timeout
        sleep_with_waiting_bar()


def sleep_with_waiting_bar(timeout: int = mb.REFRESH_TIMEOUT):
    """Print a waiting bar to the terminal.

    Args:
        timeout (int, optional): The number of seconds to wait. Defaults to mb.REFRESH_TIMEOUT.
    """

    for _ in tqdm(
        range(mb.REFRESH_TIMEOUT * 2),
        leave=False,
        ncols=80,
        bar_format="Waiting to check availability: {remaining} {bar}",
    ):
        time.sleep(0.5)


class Plan:
    def __init__(self, path: str = None):
        if path:
            if not path.endswith(".json"):
                raise ValueError(
                    "Plan file must be a JSON file. THe path should end with '.json'. For "
                    "example, 'C:/Users/Me/.monthblanc/plan.json'"
                )
            path = Path(path)
            if not path.exists():
                raise FileNotFoundError(f"Could not find plan at {path}")

        else:
            path = Path.home() / ".montblanc" / "default_plan.json"

        self.days: dict[datetime, set[Refuge]] = defaultdict(set)
        self.path: Path = path

        self.load(path)

    def check(self, min_places: int = 3):
        """Check the availability of the refuges in the plan."""
        if not self.days:
            raise ValueError("No days have been added to the plan. Use `add_day` to add days to the plan.")

        while True:
            places_found = False
            for day, refuges in self.days.items():
                for refuge in refuges:
                    if mb.alert_on_availability(day, refuge, min_places, noise=False):
                        places_found = True

            if places_found:
                mb._make_noise()

            sleep_with_waiting_bar()

    def add_day(self, date: datetime, refuges: list[int | str | Refuge], print_refuges: bool = False):
        """Add a day to the plan. If the day already exists, the refuges will replace the existing day.

        Args:
            date (datetime): The date of the day
            refuges (list[int | str | Refuge]): A list of refuges to stay at on the given date
        """
        if not refuges:
            self.days.pop(date, None)
            if print_refuges:
                print(f"Cleared {date.strftime(r'%A, %b %d, %Y')}")
            self.save()
            return

        c_refuges = [convert_refuge(refuge) for refuge in refuges]
        self.days[date] = set(c_refuges)
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
                    "refuges": [r.model_dump() for r in refuges],
                }
                for day, refuges in self.days.items()
            ]
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w") as f:
            json.dump(payload, f, indent=4)

    def load(self, path: str):
        """Load a plan from a file.

        Args:
            path (str): The path to load the plan from
        """
        path = Path(path)
        if not path.exists():
            self.days = defaultdict(set)
            return

        with open(path, "r") as f:
            payload = json.load(f)

        for day in payload["days"]:
            refuges = [Refuge.model_validate(refuge) for refuge in day["refuges"]]
            self.add_day(datetime.strptime(day["date"], r"%Y-%m-%d"), refuges)


planner = typer.Typer()

plan_path = Annotated[
    str,
    typer.Option(
        "--path",
        "-p",
        help=(
            "The filepath of the plan. Provide a full path eith a filename, including the "
            ".json file extension. If omitted, a default plan will be used. "
            "Any directories in the path will be created if they do not exist."
            "\n\n[default: ~/.montblanc/default_plan.json]"
        ),
        show_default=False,
    ),
]


@planner.command()
def check(
    path: plan_path = None,
    min_places: Annotated[
        int, typer.Option("-m", "--min-places", help="The minimum number of places to alert on.")
    ] = 3,
):
    Plan(path).check(min_places)


@planner.command(help="Add a day to the plan. A day can have zero or more refuges to check.")
def day(
    date: Annotated[
        datetime,
        typer.Argument(formats=["%Y-%m-%d", "%d/%m/%Y", "%Y.%m.%d"], help="The date.", show_default=False),
    ],
    refuges: Annotated[
        List[str],
        typer.Argument(
            help=(
                "The refuges to check. Refuges can be given as names or IDs. "
                "If a refuge is given by name, you can give a partial name and the script will try to "
                "find a match. To get a list of all refuges and their IDs, run [montblanc show]. "
                "If this day already exists in the plan, the refuges will replace the existing refuges."
                "\n\nSupplying zero refuges is allowed, and can be used to clear a day. "
                "\n\nExample: "
                '\n\n>> montblanc plan day 2024-09-11 32367 "de la Nova"'
            ),
            show_default=True,
        ),
    ] = None,
    path: plan_path = None,
):
    Plan(path).add_day(date, refuges, print_refuges=True)


@planner.command()
def show(path: plan_path = None):
    plan = Plan(path)
    for day, refuges in plan.days.items():
        print(f"{day.strftime(r'%A, %b %d, %Y')}:")
        for refuge in refuges:
            print(f"  - {refuge.name}")


app = typer.Typer()
app.add_typer(planner, name="plan")


@app.command()
def show():
    names = mb.get_refuge_names()
    print(f"Found {len(names)} refuges:")
    for name in names:
        print(f"{str(name.id)+':':<8} {name.name}")


@app.command()
def check(
    date: Annotated[datetime, typer.Argument(formats=["%Y-%m-%d", "%d/%m/%Y", "%Y.%m.%d"])],
    refuges: Annotated[List[str], typer.Argument()],
    min_places: int = 3,
):
    check_refuges(refuges=refuges, date=date, min_places=min_places)


if __name__ == "__main__":
    app()
