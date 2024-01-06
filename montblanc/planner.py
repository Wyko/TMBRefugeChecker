from datetime import datetime

import typer
from typing_extensions import Annotated

from montblanc import types
from montblanc.logic import Plan

app = typer.Typer()


@app.command()
def check(
    path: types.plan_path_arg = None,
    min_places: types.min_places_arg = 3,
    silent: types.silent_arg = False,
):
    Plan(path).check(min_places, silent=silent)


@app.command(
    help=(
        "Add a day to the plan. A day can have zero or more refuges to check."
        "\n\nExample: "
        '\n\n>> montblanc plan day 2024-09-11 32367 "de la Nova"'
    )
)
def day(
    date: Annotated[
        datetime,
        typer.Argument(
            formats=["%Y-%m-%d", "%d/%m/%Y", "%Y.%m.%d"],
            help="The date.",
            show_default=False,
        ),
    ],
    refuges: types.refuges_arg = None,
    path: types.plan_path_arg = None,
):
    Plan(path).add_day(date, refuges, print_refuges=True)


@app.command()
def show(path: types.plan_path_arg = None):
    plan = Plan(path)
    for day, refuges in plan.days.items():
        print(f"{day.strftime(r'%A, %b %d, %Y')}:")
        for refuge in refuges:
            print(f"  - {refuge.name}")
