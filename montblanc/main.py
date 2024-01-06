from datetime import datetime

import typer
from typing_extensions import Annotated

from montblanc import logic, planner, types

app = typer.Typer()
app.add_typer(planner.app, name="plan")


@app.command()
def list():
    names = logic.mb.get_refuge_names()
    print(f"Found {len(names)} refuges:")
    for name in names:
        print(f"{str(name.id)+':':<8} {name.name}")


@app.command()
def check(
    date: Annotated[datetime, typer.Argument(formats=["%Y-%m-%d", "%d/%m/%Y", "%Y.%m.%d"])],
    refuges: types.refuges_arg,
    min_places: types.min_places_arg = 3,
    silent: types.silent_arg = False,
):
    logic.check_refuges(refuges=refuges, date=date, min_places=min_places)


if __name__ == "__main__":
    app()
