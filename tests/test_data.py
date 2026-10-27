"""The data and the tools: the snapshot is the pinned one and data.py is built from it, places name the airports worked
out by hand, the fewest flights agrees with a search written apart from the verifier's, and the tools are true to the
data."""

from __future__ import annotations

import random
import re
from pathlib import Path

import pytest
from build_data import COMMIT, TARGET, build, render

from contract import Direction, NextInput, PlaceInput, PlaceKind, Status
from plugin.flights import find_airports, next_airports
from verifier.checks import ARRIVALS, DEPARTURES, expected, fewest_legs, resolve
from verifier.data import AIRPORTS, FLIGHTS

# Places worked out by hand from airports.dat, each with the kind it reads as and the airports it names.
PLACES = [
    ("HOU", PlaceKind.AIRPORT, ["HOU"]),
    (" HOU ", PlaceKind.AIRPORT, ["HOU"]),  # spaces around a code are dropped
    ("MAN", PlaceKind.AIRPORT, ["MAN"]),  # Manchester's code...
    ("Man", PlaceKind.CITY, ["MJC"]),  # ...and Man, a city in Ivory Coast
    ("Houston", PlaceKind.CITY, ["AAP", "DWH", "EFD", "HOU", "IAH", "IWS"]),
    ("houston", PlaceKind.CITY, ["AAP", "DWH", "EFD", "HOU", "IAH", "IWS"]),
    ("new  york", PlaceKind.CITY, ["JFK", "JRA", "JRB", "LGA"]),  # Newark's EWR is the city Newark
    ("London", PlaceKind.CITY, ["LCY", "LGW", "LHR", "LOZ", "LTN", "STN", "YXU"]),  # three countries
    ("London, United Kingdom", PlaceKind.CITY, ["LCY", "LGW", "LHR", "LTN", "STN"]),
    ("Portland", PlaceKind.CITY, ["PDX", "PTJ", "PWM"]),
    ("Portland, United States", PlaceKind.CITY, ["PDX", "PWM"]),
    ("portland,australia", PlaceKind.CITY, ["PTJ"]),
    ("Doncaster, Sheffield", PlaceKind.CITY, ["DSA"]),  # the comma is part of the city's name
    ("Doncaster, Sheffield, United Kingdom", PlaceKind.CITY, ["DSA"]),
    ("Sao Paulo", PlaceKind.CITY, ["CGH", "GRU"]),
    ("São Paulo", PlaceKind.CITY, ["CGH", "GRU"]),  # accents do not matter
    ("Vadso", PlaceKind.CITY, ["VDS"]),  # Vadsø
    ("Noumea", PlaceKind.CITY, ["GEA", "NOU"]),
]
# Places that name nothing: codes no airport has, then names no city has.
NO_AIRPORT = ["ZZZ", "QQQ", " ZZZ"]
NO_CITY = ["Atlantis", "hou", "Hou", "HOUS", "HO", "H0U", "", "   ", "Portland, Canada", "Portland,", "London UK"]


def fewest(origins: list[str], destinations: list[str]) -> int | None:
    """The fewest flights, read straight off FLIGHTS by growing the set of airports reached until it stops growing."""
    reached, hops = set(origins), 0
    while True:
        grown = reached | {after for before in reached for after in FLIGHTS.get(before, "").split()}
        hops += 1
        if grown & set(destinations):
            return hops
        if grown == reached:
            return None
        reached = grown


def test_the_snapshot_is_the_pinned_one_and_data_py_is_built_from_it() -> None:
    assert len(COMMIT) == 40
    assert TARGET.read_text(encoding="utf-8") == render(*build())


def test_the_data_is_well_formed() -> None:
    assert (len(AIRPORTS), len(FLIGHTS), sum(len(d.split()) for d in FLIGHTS.values())) == (6071, 3241, 37041)
    assert all(re.fullmatch(r"[A-Z]{3}", code) for code in AIRPORTS)
    for origin, destinations in FLIGHTS.items():
        codes = destinations.split()
        assert codes == sorted(set(codes)) and origin not in codes and set(codes) <= set(AIRPORTS)
    # Almost half the airports have no flight at all: those are no_flight.
    assert sum(1 for code in AIRPORTS if code not in DEPARTURES and code not in ARRIVALS) == 2814


@pytest.mark.parametrize(("place", "kind", "codes"), PLACES)
def test_a_place_names_the_airports_worked_out_by_hand(place: str, kind: PlaceKind, codes: list[str]) -> None:
    assert resolve(place) == (kind, codes)


@pytest.mark.parametrize("place", NO_AIRPORT + NO_CITY)
def test_a_place_that_names_nothing(place: str) -> None:
    assert resolve(place)[1] == []


def test_fewest_flights_agrees_with_a_separate_search() -> None:
    rng = random.Random(580)
    flying = sorted(DEPARTURES)
    counted = {"near": 0, "far": 0, "none": 0}
    for _ in range(400):
        origins, destinations = rng.sample(flying, 1), rng.sample(flying, 2)
        if set(origins) & set(destinations):
            continue
        legs = fewest_legs(origins, destinations)
        assert legs == fewest(origins, destinations)
        counted["none" if legs is None else "near" if legs <= 3 else "far"] += 1
    assert all(counted.values()), counted  # the sample holds every outcome
    assert fewest_legs(["YPO"], ["IRP"]) == fewest(["YPO"], ["IRP"]) == 13  # the longest shortest route


@pytest.mark.parametrize(
    ("origin", "destination", "status"),
    [
        ("Houston", "Chicago", Status.FOUND),  # 1 flight, HOU-MDW
        ("HOU", "London", Status.FOUND),  # 2 flights, HOU-ATL-LHR
        ("AKN", "FRA", Status.FOUND),  # 3 flights, AKN-ANC-DEN-FRA
        ("AKN", "TIA", Status.FOUND),  # 4 flights
        ("Hooper Bay", "London", Status.FOUND),  # 5 flights
        ("Portland, Australia", "PDX", Status.FOUND),  # 6 flights
        ("YPO", "IRP", Status.FOUND),  # 13 flights, the most any shortest route takes
        ("Noumea", "Paris", Status.FOUND),  # NOU flies out of New Caledonia...
        ("GEA", "CDG", Status.NO_ROUTE),  # ...GEA only to its islands
        ("CDG", "GEA", Status.NO_ROUTE),  # and only they fly to it
        ("Houston", "Neerlerit Inaat", Status.NO_ROUTE),  # CNP and OBY in Greenland fly only to each other
        ("CNP", "OBY", Status.FOUND),
        ("Man", "MAN", Status.NO_FLIGHT),  # MJC has no flight out
        ("HOU", "PTJ", Status.NO_FLIGHT),  # PTJ has no flight in
        ("London", "LHR", Status.SAME_PLACE),
        ("Paris", "Paris, France", Status.SAME_PLACE),
        ("ZZZ", "HOU", Status.NO_SUCH_AIRPORT),
        ("HOU", "ZZZ", Status.NO_SUCH_AIRPORT),
        ("Atlantis", "HOU", Status.NO_SUCH_CITY),
        ("HOU", "hou", Status.NO_SUCH_CITY),
        ("Atlantis", "ZZZ", Status.NO_SUCH_CITY),  # the origin is checked first
        ("ZZZ", "Atlantis", Status.NO_SUCH_AIRPORT),
        ("ZZZ", "ZZZ", Status.NO_SUCH_AIRPORT),  # names nothing before it is the same place
        ("Man", "Man", Status.SAME_PLACE),  # the same place before no flight
    ],
)
def test_each_trip_has_the_status_worked_out_by_hand(origin: str, destination: str, status: Status) -> None:
    assert expected(origin, destination)[0] is status


def test_finds_the_airports_of_a_place(tmp_path: Path) -> None:
    found = find_airports(PlaceInput(place="Portland, United States"), tmp_path)
    assert found.place == "Portland, United States" and found.kind is PlaceKind.CITY
    assert [(a.code, a.city, a.country) for a in found.airports] == [
        ("PDX", "Portland", "United States"),
        ("PWM", "Portland", "United States"),
    ]
    pdx = found.airports[0]
    assert (pdx.flights_out, pdx.flights_in) == (len(DEPARTURES["PDX"]), len(ARRIVALS["PDX"]))
    man = find_airports(PlaceInput(place="Man"), tmp_path).airports[0]
    assert (man.code, man.flights_out, man.flights_in) == ("MJC", 0, 0)


@pytest.mark.parametrize(
    ("place", "error"), [(p, "no such airport") for p in NO_AIRPORT] + [(p, "no such city") for p in NO_CITY]
)
def test_says_which_kind_of_place_names_nothing(place: str, error: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=error):
        find_airports(PlaceInput(place=place), tmp_path)


def reached(airports: list[str], direction: Direction, tmp_path: Path) -> list[tuple[str, str]]:
    output = next_airports(NextInput(airports=airports, direction=direction), tmp_path)
    return [(entry.airport, entry.via) for entry in output.reached]


def test_takes_one_step_forward_or_backward(tmp_path: Path) -> None:
    # Worked out by hand from routes.dat: AKN flies to ANC, DLG, PIP and WSN; PTJ to MEB alone, and nothing to PTJ.
    assert reached(["AKN"], Direction.FORWARD, tmp_path) == [
        ("ANC", "AKN"),
        ("DLG", "AKN"),
        ("PIP", "AKN"),
        ("WSN", "AKN"),
    ]
    assert reached(["PTJ"], Direction.FORWARD, tmp_path) == [("MEB", "PTJ")]
    assert reached(["PTJ"], Direction.BACKWARD, tmp_path) == []
    assert reached(["MJC"], Direction.FORWARD, tmp_path) == []
    # CNP and OBY fly only to each other: asked together, neither is reached.
    assert reached(["CNP", "OBY"], Direction.FORWARD, tmp_path) == []
    assert reached(["CNP"], Direction.BACKWARD, tmp_path) == [("OBY", "CNP")]


def test_a_step_reaches_each_airport_once_by_the_first_via(tmp_path: Path) -> None:
    steps = reached(["IAH", "HOU"], Direction.FORWARD, tmp_path)
    airports = [airport for airport, _ in steps]
    assert airports == sorted(set(airports)) and not {"HOU", "IAH"} & set(airports)
    assert set(airports) == (set(DEPARTURES["HOU"]) | set(DEPARTURES["IAH"])) - {"HOU", "IAH"}
    for airport, via in steps:
        # HOU comes first by code: it is the via whenever it flies there.
        assert via == ("HOU" if airport in DEPARTURES["HOU"] else "IAH")
    for airport, via in reached(["MDW"], Direction.BACKWARD, tmp_path):
        assert via == "MDW" and "MDW" in DEPARTURES[airport]


@pytest.mark.parametrize(
    ("codes", "error"),
    [
        (["ZZZ"], "no such airport"),
        (["HOU", "ZZZ"], "no such airport"),
        ([], "at least one"),
        (["hou"], "not IATA codes"),
        (["HOU", "HOU"], "once"),
    ],
)
def test_refuses_codes_that_are_not_airports(codes: list[str], error: str, tmp_path: Path) -> None:
    for direction in Direction:
        with pytest.raises(ValueError, match=error):
            next_airports(NextInput(airports=codes, direction=direction), tmp_path)
