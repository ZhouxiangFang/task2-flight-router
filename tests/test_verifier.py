"""The verifier, called as NanoAgent's sandbox calls it, with contract instances built from JSON: every answer to the
task and every tool output, judged against the definition of a valid route and the data. The search the task's
instructions describe, played through the tools, earns a valid verdict on every sampled trip."""

from __future__ import annotations

import random
from itertools import pairwise
from pathlib import Path

import pytest
from slimconfig import build_output, plain_output
from test_data import NO_AIRPORT, NO_CITY, PLACES

import verifier
from contract import TOOLS, Direction, NextInput, PlaceInput, RouteInput, RouteOutput, Status, Tool
from plugin.flights import find_airports, next_airports
from verifier.checks import DEPARTURES, expected

STATUSES = [status.value for status in Status]


def verify(origin: str, destination: str, status: str, airports, workspace: Path = Path(".")) -> dict:
    """The verdict on an answer to the task; there is no reference."""
    output = build_output({"status": status, "airports": list(airports)}, RouteOutput)
    arguments = build_output({"origin": origin, "destination": destination}, RouteInput)
    return verifier.verify_task("plan-flight-route", arguments, output, None, str(workspace))


def flies(route: list[str]) -> bool:
    return all(after in DEPARTURES.get(before, []) for before, after in pairwise(route))


def shortest(origins: list[str], destinations: list[str]) -> list[str]:
    """A shortest route, by a breadth-first search that keeps each airport's predecessor."""
    before = {origin: "" for origin in origins}
    frontier = list(origins)
    while frontier:
        following = []
        for code in frontier:
            for after in DEPARTURES.get(code, []):
                if after not in before:
                    before[after] = code
                    following.append(after)
                    if after in destinations:
                        route = [after]
                        while before[route[-1]]:
                            route.append(before[route[-1]])
                        return route[::-1]
        frontier = following
    raise AssertionError("no route")


@pytest.mark.parametrize(
    ("origin", "destination", "route"),
    [
        ("Houston", "Chicago", ["HOU", "MDW"]),
        ("houston", "chicago", ["HOU", "ATL", "ORD"]),  # not the shortest, still a route
        ("HOU", "London", ["HOU", "ATL", "LHR"]),
        ("HOU", "London", ["HOU", "ATL", "JFK", "BOS", "LHR"]),  # 4 flights where 2 would do
        ("AKN", "FRA", ["AKN", "ANC", "DEN", "FRA"]),
        ("AKN", "TIA", ["AKN", "ANC", "DEN", "FRA", "TIA"]),  # 4 flights, the fewest
        ("Portland, United States", "London", ["PDX", "SEA", "LHR"]),
        ("Noumea", "Paris", ["NOU", "NRT", "CDG"]),
        ("CNP", "OBY", ["CNP", "OBY"]),
    ],
)
def test_accepts_a_route_of_real_flights(origin: str, destination: str, route: list[str]) -> None:
    assert flies(route)
    verdict = verify(origin, destination, "found", route)
    assert verdict["valid"] is True and verdict["score"] == 1.0, verdict


def test_accepts_a_route_however_many_flights_it_takes() -> None:
    route = shortest(["YPO"], ["IRP"])
    assert len(route) == 14 and flies(route)  # 13 flights, the most any shortest route takes
    verdict = verify("YPO", "IRP", "found", route)
    assert verdict["valid"] is True and "the fewest is 13" in verdict["message"]
    # A longer detour through more airports is a route too.
    detour = ["HOU", "ATL", "JFK", "BOS", "ORD", "DEN", "SEA", "ANC", "FAI"]
    assert flies(detour) and verify("HOU", "FAI", "found", detour)["valid"] is True


@pytest.mark.parametrize(
    ("origin", "destination", "route", "message"),
    [
        ("HOU", "MDW", ["HOU"], "at least two airports"),
        ("HOU", "MDW", [], "at least two airports"),
        ("HOU", "MDW", ["HOU", "ATL", "HOU", "MDW"], "none twice"),  # a loop
        ("HOU", "MDW", ["HOU", "ZZZ", "MDW"], "known IATA code"),
        ("HOU", "MDW", ["hou", "MDW"], "known IATA code"),
        ("HOU", "MDW", ["IAH", "MDW"], "not an origin airport"),  # Houston's, but not the one asked for
        ("Houston", "Chicago", ["HOU", "ATL"], "not a destination airport"),
        ("Houston", "Chicago", ["ATL", "ORD"], "not an origin airport"),
        ("London", "Portland, United States", ["LHR", "PTJ"], "not a destination airport"),  # the other Portland
    ],
)
def test_refuses_a_route_that_is_not_one(origin, destination, route, message) -> None:
    verdict = verify(origin, destination, "found", route)
    assert verdict["valid"] is False and verdict["score"] == 0.0 and message in verdict["message"], verdict


def test_gives_partial_credit_for_a_route_with_made_up_flights() -> None:
    # HOU-ATL is real, ATL-PDX is real, PDX-TIA is not.
    assert flies(["HOU", "ATL", "PDX"]) and not flies(["PDX", "TIA"])
    verdict = verify("HOU", "TIA", "found", ["HOU", "ATL", "PDX", "TIA"])
    assert verdict["valid"] is False and verdict["score"] == pytest.approx(2 / 3)
    assert verdict["details"]["missing"] == ["PDX-TIA"]
    # GEA flies only within New Caledonia: no flight to Paris at all.
    verdict = verify("GEA", "CDG", "found", ["GEA", "CDG"])
    assert verdict["valid"] is False


@pytest.mark.parametrize(
    ("origin", "destination", "status"),
    [
        ("ZZZ", "HOU", "no_such_airport"),
        ("HOU", "QQQ", "no_such_airport"),
        ("Atlantis", "HOU", "no_such_city"),
        ("HOU", "hou", "no_such_city"),
        ("Atlantis", "ZZZ", "no_such_city"),
        ("ZZZ", "Atlantis", "no_such_airport"),
        ("London", "LHR", "same_place"),
        ("Paris", "Paris, France", "same_place"),
        ("Man", "MAN", "no_flight"),
        ("HOU", "PTJ", "no_flight"),
        ("GEA", "CDG", "no_route"),
        ("CDG", "GEA", "no_route"),
        ("Houston", "Neerlerit Inaat", "no_route"),
    ],
)
def test_accepts_only_the_status_the_trip_has(origin: str, destination: str, status: str) -> None:
    verdict = verify(origin, destination, status, [])
    assert verdict["valid"] is True and verdict["score"] == 1.0, verdict
    for other in STATUSES:
        if other != status:
            assert verify(origin, destination, other, [])["valid"] is False
    # An airport list goes only with found.
    verdict = verify(origin, destination, status, ["HOU", "MDW"])
    assert verdict["valid"] is False and "empty" in verdict["message"]


def test_a_long_route_is_found_not_no_route() -> None:
    assert verify("AKN", "TIA", "no_route", [])["valid"] is False
    assert verify("YPO", "IRP", "no_route", [])["valid"] is False
    assert verify("YPO", "IRP", "found", [])["valid"] is False  # found needs the route


@pytest.mark.parametrize("place", NO_AIRPORT)
def test_a_code_no_airport_has_is_no_such_airport(place: str) -> None:
    assert verify(place, "HOU", "no_such_airport", [])["valid"] is True
    assert verify("HOU", place, "no_such_airport", [])["valid"] is True
    assert verify(place, "HOU", "no_such_city", [])["valid"] is False


@pytest.mark.parametrize("place", NO_CITY)
def test_a_name_no_city_has_is_no_such_city(place: str) -> None:
    assert verify(place, "HOU", "no_such_city", [])["valid"] is True
    assert verify("HOU", place, "no_such_city", [])["valid"] is True
    assert verify(place, "HOU", "no_such_airport", [])["valid"] is False


def test_agrees_with_the_shortest_route_on_sampled_trips() -> None:
    rng = random.Random(580)
    places = [place for place, _, _ in PLACES] + sorted(DEPARTURES)
    seen = set()
    for _ in range(300):
        origin, destination = rng.sample(places, 2)
        status, _, origins, destinations = expected(origin, destination)
        seen.add(status)
        if status is not Status.FOUND:
            assert verify(origin, destination, status.value, [])["valid"] is True
            continue
        route = shortest(origins, destinations)
        assert verify(origin, destination, "found", route)["valid"] is True
        if len(route) > 2 or not flies(route[::-1]):
            assert verify(origin, destination, "found", route[::-1])["valid"] is False  # flown backwards
        assert verify(origin, destination, "no_route", [])["valid"] is False
    assert {Status.FOUND, Status.NO_ROUTE, Status.NO_FLIGHT} <= seen


def follow_instructions(origin: str, destination: str, tmp_path: Path) -> tuple[dict, int]:
    """The answer the task's instructions lead to, through the tools, and how many turns of next_airports it took."""
    places = []
    for place in (origin, destination):
        try:
            places.append(find_airports(PlaceInput(place=place), tmp_path).airports)
        except ValueError as error:
            status = "no_such_airport" if str(error).startswith("no such airport") else "no_such_city"
            return {"status": status, "airports": []}, 0
    origins, destinations = ([airport.code for airport in found] for found in places)
    if set(origins) & set(destinations):
        return {"status": "same_place", "airports": []}, 0
    if all(a.flights_out == 0 for a in places[0]) or all(a.flights_in == 0 for a in places[1]):
        return {"status": "no_flight", "airports": []}, 0
    maps = {Direction.FORWARD: dict.fromkeys(origins, ""), Direction.BACKWARD: dict.fromkeys(destinations, "")}
    frontiers = {Direction.FORWARD: origins, Direction.BACKWARD: destinations}
    turns = 0
    while True:
        sizes = {direction: len(frontier) for direction, frontier in frontiers.items()}
        if max(sizes.values()) <= 10:
            directions = list(Direction)
        else:
            directions = [min(sizes, key=lambda direction: (sizes[direction], direction.value == "backward"))]
        turns += 1
        for direction in directions:
            given = NextInput(airports=frontiers[direction], direction=direction)
            new = [r for r in next_airports(given, tmp_path).reached if r.airport not in maps[direction]]
            if not new:
                return {"status": "no_route", "airports": []}, turns
            maps[direction].update((r.airport, r.via) for r in new)
            frontiers[direction] = [r.airport for r in new]
        met = sorted(set(maps[Direction.FORWARD]) & set(maps[Direction.BACKWARD]))
        if met:
            route = [met[0]]
            while maps[Direction.FORWARD][route[0]]:
                route.insert(0, maps[Direction.FORWARD][route[0]])
            while maps[Direction.BACKWARD][route[-1]]:
                route.append(maps[Direction.BACKWARD][route[-1]])
            return {"status": "found", "airports": route}, turns


def test_the_instructions_search_earns_a_valid_verdict(tmp_path: Path) -> None:
    rng = random.Random(580)
    places = [place for place, _, _ in PLACES] + sorted(DEPARTURES)
    trips = [tuple(rng.sample(places, 2)) for _ in range(300)]
    trips += [("YPO", "IRP"), ("HPB", "IVL"), ("GEA", "CDG"), ("CDG", "GEA"), ("Houston", "Neerlerit Inaat")]
    most = 0
    for origin, destination in trips:
        answer, turns = follow_instructions(origin, destination, tmp_path)
        verdict = verify(origin, destination, answer["status"], answer["airports"])
        assert verdict["valid"] is True, (origin, destination, answer, verdict)
        most = max(most, turns)
    assert most == 7  # YPO to IRP, 13 flights, the longest


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {"status": "found"},
        {"airports": ["HOU", "MDW"]},
        {"status": None, "airports": []},
        {"status": "found", "airports": None},
        {"status": "FOUND", "airports": ["HOU", "MDW"]},
        {"status": "too_many_legs", "airports": []},
        {"status": True, "airports": []},
        {"status": "found", "airports": "HOU,MDW"},
        {"status": "found", "airports": [1, 2]},
        {"status": "found", "airports": ["HOU", None]},
        {"status": "found", "airports": [["HOU", "MDW"]]},
        {"status": "found", "airports": [{"code": "HOU"}, {"code": "MDW"}]},
        {"status": "found", "airports": ["HOU", "MDW"], "legs": 1},
    ],
)
def test_a_malformed_answer_never_reaches_the_verifier(answer: dict) -> None:
    # NanoAgent builds every answer into its contract class first, and refuses one that does not fit.
    with pytest.raises(ValueError):
        build_output(answer, RouteOutput)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"origin": "HOU"},
        {"origin": None, "destination": "MDW"},
        {"origin": ["HOU"], "destination": "MDW"},
        {"origin": "HOU", "destination": "MDW", "max_legs": 4},
    ],
)
def test_a_malformed_task_input_is_refused(arguments: dict) -> None:
    with pytest.raises(ValueError):
        build_output(arguments, RouteInput)


def check(tool: str, value: dict, output: dict | None = None) -> bool:
    """Whether verify_input (without ``output``) or verify_output (with it) approves a tool call."""
    given, made = TOOLS[Tool(tool)]
    if output is None:
        return verifier.verify_input(tool, build_output(value, given))["valid"]
    return verifier.verify_output(tool, build_output(value, given), build_output(output, made), ".")["valid"]


def test_checks_tool_inputs() -> None:
    for place in ["HOU", "Houston", "", *NO_AIRPORT, *NO_CITY]:
        assert check("find_airports", {"place": place}) is True  # the tool says when a place names nothing
    for direction in ["forward", "backward"]:
        # Well formed: the tool itself says ZZZ is no airport.
        assert check("next_airports", {"airports": ["HOU", "ZZZ"], "direction": direction}) is True
        for bad in [[], ["hou"], ["HOU", "HOU"], ["Houston"], ["HOU "]]:
            assert check("next_airports", {"airports": bad, "direction": direction}) is False
    with pytest.raises(ValueError):
        check("next_airports", {"airports": ["HOU"], "direction": "out"})  # no such direction


@pytest.mark.parametrize("place", [place for place, _, _ in PLACES])
def test_approves_every_true_find_airports_output(place: str, tmp_path: Path) -> None:
    output = plain_output(find_airports(PlaceInput(place=place), tmp_path))
    assert check("find_airports", {"place": place}, output) is True


@pytest.mark.parametrize("direction", ["forward", "backward"])
@pytest.mark.parametrize("airports", [["HOU", "IAH"], ["MJC"], ["PTJ"], ["CNP", "OBY"], ["YPO"], ["LHR", "JFK"]])
def test_approves_every_true_next_airports_output(airports: list[str], direction: str, tmp_path: Path) -> None:
    given = {"airports": airports, "direction": direction}
    output = plain_output(next_airports(build_output(given, NextInput), tmp_path))
    assert check("next_airports", given, output) is True


@pytest.mark.parametrize(
    ("tool", "given", "output"),
    [
        (
            "find_airports",
            {"place": "Man"},
            {
                "place": "Man",
                "kind": "airport",
                "airports": [
                    {"code": "MJC", "city": "Man", "country": "Cote d'Ivoire", "flights_out": 0, "flights_in": 0}
                ],
            },
        ),  # the wrong kind
        (
            "find_airports",
            {"place": "Portland"},
            {
                "place": "Portland",
                "kind": "city",
                "airports": [
                    {"code": "PDX", "city": "Portland", "country": "United States", "flights_out": 1, "flights_in": 1}
                ],
            },
        ),  # airports dropped, counts made up
        ("find_airports", {"place": "ZZZ"}, {"place": "ZZZ", "kind": "airport", "airports": []}),  # must fail
        ("next_airports", {"airports": ["PTJ"], "direction": "forward"}, {"reached": []}),  # dropped
        (
            "next_airports",
            {"airports": ["PTJ"], "direction": "backward"},
            {"reached": [{"airport": "MEB", "via": "PTJ"}]},
        ),
        ("next_airports", {"airports": ["ZZZ"], "direction": "forward"}, {"reached": []}),  # must fail
        (
            "next_airports",
            {"airports": ["AKN"], "direction": "forward"},
            {"reached": [{"airport": "DLG", "via": "AKN"}, {"airport": "ANC", "via": "AKN"}]},
        ),  # unsorted, two dropped
        (
            "next_airports",
            {"airports": ["CNP", "OBY"], "direction": "forward"},
            {"reached": [{"airport": "OBY", "via": "CNP"}]},
        ),  # an airport asked about
        (
            "next_airports",
            {"airports": ["MJC"], "direction": "forward"},
            {"reached": [{"airport": "CDG", "via": "MJC"}]},
        ),  # made up
    ],
)
def test_refuses_a_tool_output_that_is_not_the_data(tool: str, given: dict, output: dict) -> None:
    assert check(tool, given, output) is False
