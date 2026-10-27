"""The tools that read the airports and flights, from verifier/data.py: the one copy, which the verifier also judges
by. Places are read and codes checked by verifier/checks.py's rules, so a tool and a verdict never disagree on them."""

from __future__ import annotations

from pathlib import Path

from contract import Airport, NextInput, NextOutput, PlaceInput, PlaceKind, PlaceOutput, Reached
from verifier.checks import AIRPORTS, ARRIVALS, DEPARTURES, codes_problem, next_reached, resolve


def find_airports(given: PlaceInput, workspace: Path) -> PlaceOutput:
    kind, codes = resolve(given.place)
    if not codes and kind is PlaceKind.AIRPORT:
        raise ValueError(f"no such airport: no airport has the IATA code {given.place.strip()!r}")
    if not codes:
        raise ValueError(
            f"no such city: no city is named {given.place!r}. A city may be followed by its country after a comma, "
            "such as 'Portland, United States'; an airport is its IATA code in three capital letters, such as 'HOU'"
        )
    airports = [
        Airport(
            code=code,
            city=AIRPORTS[code][0],
            country=AIRPORTS[code][1],
            flights_out=len(DEPARTURES.get(code, [])),
            flights_in=len(ARRIVALS.get(code, [])),
        )
        for code in codes
    ]
    return PlaceOutput(place=given.place, kind=kind, airports=airports)


def next_airports(given: NextInput, workspace: Path) -> NextOutput:
    problem = codes_problem(given.airports)
    if problem:
        raise ValueError(problem)
    unknown = sorted(code for code in given.airports if code not in AIRPORTS)
    if unknown:
        raise ValueError(f"no such airport: no airport has the IATA code(s) {unknown}")
    reached = next_reached(given.airports, given.direction)
    return NextOutput(reached=[Reached(airport=airport, via=via) for airport, via in reached.items()])
