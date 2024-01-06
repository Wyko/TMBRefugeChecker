from typing import List

import typer
from typing_extensions import Annotated

plan_path_arg = Annotated[
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

silent_arg = Annotated[
    bool,
    typer.Option(
        "--silent",
        "-s",
        help=("Do not make any noise when availability is found. By default, a noise will be made."),
        show_default=False,
    ),
]

min_places_arg = Annotated[
    int,
    typer.Option("-m", "--min-places", help="The minimum number of places to alert on."),
]

refuges_arg = Annotated[
    List[str],
    typer.Argument(
        help=(
            "The refuges to check. Refuges can be given as names or IDs. "
            "If a refuge is given by name, you can give a partial name and the script will try to "
            "find a match. To get a list of all refuges and their IDs, run [montblanc show]. "
            "If this day already exists in the plan, the refuges will replace the existing refuges."
            "\n\nSupplying zero refuges is allowed, and can be used to clear a day. "
        ),
        show_default=True,
    ),
]
