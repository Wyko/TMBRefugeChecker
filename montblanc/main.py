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
from datetime import datetime, timedelta
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
        response: list[dict[str, str]] = json.loads(r.text.strip("()[]\r\n ;"))[
            "ListeId"
        ]
        for loc in response:
            loc["Nom"] = loc["Nom"].replace("&nbsp;", "'").strip("- '")
            loc["Id"] = loc["Id"].strip().split(",")
            loc["Id"] = [int(i) for i in loc["Id"]]

        return response

    def alert_on_availability(
        self, date: datetime, refuge: Refuge, min_places: int = 3
    ):
        """Print an alert if there are more than `min_places` places available at `refuge_id` on `date`"""
        availability = self.get_availability(date, refuge.id)
        if availability["closed"]:
            print(
                f"Refuge {refuge.name} is closed on {date.strftime(r'%A, %b %d, %Y')}"
            )
            return

        if availability["places"] > min_places:
            print(
                f"!!! Refuge {refuge.name} has {availability['places']} places left on {date.strftime(r'%A, %b %d, %Y')} !!!"
            )
            self._make_noise()
            return

        print(
            f"{refuge.name} has {availability['places']} places left on {date.strftime(r'%A, %b %d, %Y')}"
        )

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


def check_refuges(
    refuges: list[int | str | Refuge], date: datetime, min_places: int = 3
):
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
        for _ in tqdm(
            range(mb.REFRESH_TIMEOUT * 2),
            leave=False,
            ncols=80,
            bar_format="Waiting to check availability: {remaining} {bar}",
        ):
            time.sleep(0.5)


def convert_refuge(refuge: int | str | Refuge):
    try:
        refuge = int(refuge)
    except ValueError:
        pass

    if isinstance(refuge, int):
        return mb.refuge_by_id(refuge)
    elif isinstance(refuge, Refuge):
        return refuge
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
                    mb.alert_on_availability(
                        date, mb.refuge_by_id(refuge_id), min_places
                    )

        # Wait for the refresh timeout
        for _ in tqdm(
            range(mb.REFRESH_TIMEOUT * 2),
            leave=False,
            ncols=80,
            bar_format="Waiting to check availability: {remaining} {bar}",
        ):
            time.sleep(0.5)


app = typer.Typer()


@app.command()
def show():
    names = mb.get_refuge_names()
    print(f"Found {len(names)} refuges:")
    for name in names:
        print(f"{str(name.id)+':':<8} {name.name}")


@app.command()
def check(
    date: Annotated[
        datetime, typer.Argument(formats=["%Y-%m-%d", "%d/%m/%Y", "%Y.%m.%d"])
    ],
    refuges: Annotated[List[str], typer.Argument()],
    min_places: int = 3,
):
    check_refuges(refuges=refuges, date=date, min_places=min_places)


if __name__ == "__main__":
    app()
