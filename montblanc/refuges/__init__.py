from typing import Literal

import pydantic


class Refuge(pydantic.BaseModel):
    id: int
    name: str

    special: Literal[True, False] = False
    """Whether the refuge is special, i.e. not found on montourdumontblanc.com."""

    def check_availability(self) -> bool:
        """Check if there is availability at the refuge.

        This method should return a dict with at least the following keys:

        {
            "places": Int or None,
            "closed": Bool or None,
            "retrieved": datetime,
            "bookable": Bool,  # If the booking system is even open yet.
        }

        This method should be overridden by subclasses.
        """
        raise NotImplementedError

    def __hash__(self) -> int:
        return hash((self.id, self.name))
