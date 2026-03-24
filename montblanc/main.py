from datetime import datetime
import webbrowser

import typer
import uvicorn
from typing_extensions import Annotated

from montblanc import logic, planner, types

app = typer.Typer()
app.add_typer(planner.app, name="plan")


@app.command()
def list():
    names = logic.get_all_refuge_ids()
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


@app.command()
def web(
    port: Annotated[int, typer.Option(help="Port to run the server on.")] = 8000,
    no_browser: Annotated[bool, typer.Option("--no-browser", help="Don't open the browser automatically.")] = False,
):
    """Start the web UI for refuge availability checking.

    Args:
        port (int): Port to run the server on. Defaults to 8000.
        no_browser (bool): If set, don't open the browser automatically.
    """
    if not no_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run("montblanc.web.app:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
