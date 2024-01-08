from datetime import datetime

import httpx

from montblanc.refuges import Refuge


# Create the refuge object
class LacBlanc(Refuge):
    def __init__(self):
        super().__init__(name="Refuge du Lac Blanc", id="90001", special=True)

    def check_availability(self) -> bool:
        """Check if there is availability at the refuge.

        This method should return a dict with at least the following keys:

        {
            "places": Int or None,
            "closed": Bool or None,
            "retrieved": datetime,
            "bookable": Bool,  # If the booking system is even open yet.
        }

        """

        is_open = self.check_if_booking_open()

        return {
            "places": None,
            "closed": None,
            "retrieved": datetime.utcnow(),
            "bookable": is_open,
        }

    def check_if_booking_open(self):
        """Check if booking is open for Lac Blanc refuge."""

        # Get the booking page
        try:
            r = httpx.get("https://refuge-lac-blanc.fr/en/booking/")
            r.raise_for_status()
            # Check if the booking is open
            return "Reservations are not possible at this time" not in r.text
        except httpx.HTTPError:
            print("### Error while checking if booking is open for Lac Blanc refuge")
            return False


refuge = LacBlanc
