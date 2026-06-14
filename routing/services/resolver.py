import re

from rest_framework.exceptions import ValidationError

from routing.models import Location, PlaceLocation, PostalCodeLocation

from .geo import is_us_coordinate, normalize_location


STATE_ZIP_PATTERN = re.compile(r"^(?:(?P<state>[a-z]{2})\s+)?(?P<zip>\d{5})(?:-\d{4})?$")
PLACE_STATE_PATTERN = re.compile(r"^(?P<place>.+?)\s+(?P<state>[a-z]{2})$")


def resolve_location(value):
    if isinstance(value, dict):
        try:
            latitude = float(value["latitude"])
            longitude = float(value["longitude"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError("Coordinates require numeric latitude and longitude.")
        if not is_us_coordinate(latitude, longitude):
            raise ValidationError("Coordinates must be within the USA.")
        return {
            "display_name": f"{latitude:.6f}, {longitude:.6f}",
            "coordinates": [longitude, latitude],
            "source": "coordinates",
        }

    if not isinstance(value, str) or not value.strip():
        raise ValidationError("Location must be text, a US postal code, or coordinates.")

    normalized = normalize_location(value)
    postal_match = STATE_ZIP_PATTERN.fullmatch(normalized)
    if postal_match:
        postal_code = postal_match.group("zip")
        requested_state = postal_match.group("state")
        candidates = PostalCodeLocation.objects.filter(postal_code=postal_code)
        if requested_state:
            candidates = candidates.filter(state__iexact=requested_state)
        candidate_count = candidates.count()
        if candidate_count == 1:
            location = candidates.first()
            return {
                "display_name": location.display_name,
                "coordinates": [location.longitude, location.latitude],
                "source": "postal_code",
            }
        if candidate_count > 1:
            candidate_names = ", ".join(
                candidates.order_by("display_name").values_list("display_name", flat=True)
            )
            raise ValidationError(
                f"Postal code '{postal_code}' is ambiguous. Candidates: {candidate_names}."
            )

        all_candidates = PostalCodeLocation.objects.filter(postal_code=postal_code)
        if requested_state and all_candidates.exists():
            states = sorted({candidate.state for candidate in all_candidates if candidate.state})
            state_text = ", ".join(states) or "no standard state"
            raise ValidationError(
                f"Postal code '{postal_code}' does not match {requested_state.upper()}; "
                f"available state values: {state_text}."
            )

        # Backward-compatible fallback for locally imported location files.
        location = Location.objects.filter(
            normalized_text=postal_code,
            kind="postal_code",
        ).first()
        if location is None:
            raise ValidationError(
                f"Postal code '{postal_code}' was not found in the local US geocoding database."
            )
        if requested_state and location.state.lower() != requested_state:
            raise ValidationError(
                f"Postal code '{postal_code}' belongs to {location.state}, not {requested_state.upper()}."
            )
        return {
            "display_name": location.display_name,
            "coordinates": [location.longitude, location.latitude],
            "source": location.kind,
        }

    location = Location.objects.filter(normalized_text=normalized).first()
    if location is not None:
        return {
            "display_name": location.display_name,
            "coordinates": [location.longitude, location.latitude],
            "source": location.kind,
        }

    place_state_match = PLACE_STATE_PATTERN.fullmatch(normalized)
    if place_state_match:
        place = PlaceLocation.objects.filter(
            normalized_name=place_state_match.group("place"),
            state__iexact=place_state_match.group("state"),
        ).first()
        if place is not None:
            return {
                "display_name": place.display_name,
                "coordinates": [place.longitude, place.latitude],
                "source": "place",
            }

    places = PlaceLocation.objects.filter(normalized_name=normalized).order_by(
        "-postal_code_count", "state"
    )
    count = places.count()
    if count == 1:
        place = places.first()
        return {
            "display_name": place.display_name,
            "coordinates": [place.longitude, place.latitude],
            "source": "place",
        }
    if count > 1:
        ranked = list(places[:2])
        if (
            ranked[0].postal_code_count >= 3
            and ranked[0].postal_code_count >= ranked[1].postal_code_count * 3
        ):
            place = ranked[0]
            return {
                "display_name": place.display_name,
                "coordinates": [place.longitude, place.latitude],
                "source": "dominant_place",
            }
        candidates = ", ".join(places.values_list("display_name", flat=True))
        raise ValidationError(
            f"Location '{value}' is ambiguous. Include a state abbreviation. Candidates: {candidates}."
        )
    raise ValidationError(
        f"Location '{value}' was not found in the local US geocoding database."
    )
