"""Checks shared by the verifiers and the tools: how a place names airports, and what the flights allow. Pure
functions of their arguments and data.py."""

import re
import unicodedata
from collections import Counter
from itertools import pairwise

from contract import Direction, PlaceKind, Status

from .data import AIRPORTS, FLIGHTS

CODE = re.compile(r"^[A-Z]{3}$")
# Lowercase letters that no accent can be dropped from, as plain Latin: Vadsø is Vadso.
LETTERS = str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "đ": "d", "ð": "d", "þ": "th", "ł": "l", "ı": "i"})


def inverted(departures):
    """code -> the sorted codes that fly to it, from code -> the codes it flies to."""
    arrivals = {}
    for origin, destinations in departures.items():
        for destination in destinations:
            arrivals.setdefault(destination, []).append(origin)
    return {code: sorted(origins) for code, origins in sorted(arrivals.items())}


def cities(airports):
    """Folded city name -> the sorted codes of its airports, in every country that has a city of that name."""
    named = {}
    for code, (city, country) in airports.items():
        if city:
            named.setdefault(folded(city), []).append(code)
    return named


def folded(text):
    """``text`` as names are compared: accents dropped, case folded, letters such as ø written in plain Latin
    (LETTERS), runs of spaces made one."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().translate(LETTERS)
    return " ".join(plain.split())


# code -> the sorted codes it flies to, and code -> the sorted codes that fly to it; an airport with none is absent.
DEPARTURES = {code: destinations.split() for code, destinations in FLIGHTS.items()}
ARRIVALS = inverted(DEPARTURES)
CITIES = cities(AIRPORTS)


def result(valid, message, *, score=None, **details):
    return {
        "valid": valid,
        "score": float(valid) if score is None else score,
        "message": message,
        "details": details,
    }


def resolve(place):
    """How ``place`` reads, a PlaceKind, and the sorted codes of every airport it names: empty when none.

    Three capital letters (spaces around them aside) are an airport's IATA code. Anything else is a city name, matched
    whatever its case and accents; if no city has the whole name, a last comma may split it into a city and its
    country ("Portland, United States").
    """
    text = place.strip()
    if CODE.fullmatch(text):
        return PlaceKind.AIRPORT, [text] if text in AIRPORTS else []
    codes = CITIES.get(folded(text), [])
    if not codes and "," in text:
        city, country = text.rsplit(",", 1)
        codes = [code for code in CITIES.get(folded(city), []) if folded(AIRPORTS[code][1]) == folded(country)]
    return PlaceKind.CITY, codes


def codes_problem(codes):
    """What makes ``codes`` no list of airport codes to ask about, or None."""
    if not codes:
        return "name at least one airport"
    malformed = [code for code in codes if not CODE.fullmatch(code)]
    if malformed:
        return f"{malformed} are not IATA codes: an airport is three capital letters, such as HOU"
    repeated = sorted(code for code, count in Counter(codes).items() if count > 1)
    if repeated:
        return f"name each airport once: {repeated} are repeated"
    return None


def next_reached(airports, direction):
    """Every airport one nonstop flight from ``airports`` in ``direction`` and not among them, sorted, each mapped to
    the first of ``airports`` by code that it is reached from."""
    flights = DEPARTURES if direction is Direction.FORWARD else ARRIVALS
    asked = set(airports)
    reached = {}
    for via in sorted(asked):
        for airport in flights.get(via, ()):
            if airport not in asked and airport not in reached:
                reached[airport] = via
    return dict(sorted(reached.items()))


def fewest_legs(origins, destinations):
    """The fewest nonstop flights from one of ``origins`` to one of ``destinations``, or None when no route joins them
    (breadth-first search, one flight further each round, until nothing new is reached)."""
    targets = set(destinations)
    reached = set(origins)
    frontier = set(origins)
    legs = 0
    while frontier:
        legs += 1
        frontier = {after for before in frontier for after in DEPARTURES.get(before, ())} - reached
        if frontier & targets:
            return legs
        reached |= frontier
    return None


def expected(origin, destination):
    """The status the trip from ``origin`` to ``destination`` has, why, and the airports each names.

    The checks go in this order, the first that holds deciding: the origin names nothing, the destination names
    nothing, they share an airport, no origin airport has a flight out, no destination airport has a flight in, and
    no route of any length joins them.
    """
    named = []
    for role, place in (("origin", origin), ("destination", destination)):
        kind, codes = resolve(place)
        if not codes:
            status = Status.NO_SUCH_AIRPORT if kind is PlaceKind.AIRPORT else Status.NO_SUCH_CITY
            return status, f"the {role} {place!r} names no {kind.value}", [], []
        named.append(codes)
    origins, destinations = named
    shared = sorted(set(origins) & set(destinations))
    if shared:
        return Status.SAME_PLACE, f"{shared[0]} is both an origin and a destination airport", origins, destinations
    if not any(code in DEPARTURES for code in origins):
        return Status.NO_FLIGHT, f"no origin airport {origins} has a flight out", origins, destinations
    if not any(code in ARRIVALS for code in destinations):
        return Status.NO_FLIGHT, f"no destination airport {destinations} has a flight in", origins, destinations
    legs = fewest_legs(origins, destinations)
    if legs is None:
        return Status.NO_ROUTE, "no route of any length joins them", origins, destinations
    return Status.FOUND, f"a route of {legs} flight(s) is the shortest", origins, destinations


def route_problem(route, origins, destinations):
    """How ``route`` fails to fly from one of ``origins`` to one of ``destinations`` by nonstop flights, as many as
    it takes, as a verdict's message, score and details, or None."""
    legs = len(route) - 1
    if legs < 1:
        return {"message": "a route needs at least two airports, an origin and a destination", "airports": route}
    unknown = sorted({code for code in route if code not in AIRPORTS})
    repeated = sorted(code for code, count in Counter(route).items() if count > 1)
    if unknown or repeated:
        return {
            "message": "every airport must be a known IATA code, none twice",
            "unknown": unknown,
            "repeated": repeated,
        }
    if route[0] not in origins:
        return {"message": f"the route starts at {route[0]}, which is not an origin airport", "origins": origins}
    if route[-1] not in destinations:
        return {
            "message": f"the route ends at {route[-1]}, which is not a destination airport",
            "destinations": destinations,
        }
    missing = [f"{before}-{after}" for before, after in pairwise(route) if after not in DEPARTURES.get(before, ())]
    if missing:
        return {
            "message": f"{len(missing)} of the route's {legs} flights do not exist",
            "missing": missing,
            "score": 1 - len(missing) / legs,
        }
    return None
