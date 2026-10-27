"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    FIND_AIRPORTS = "find_airports"
    NEXT_AIRPORTS = "next_airports"


class Task(Enum):
    PLAN_FLIGHT_ROUTE = "plan-flight-route"


class Status(Enum):
    FOUND = "found"
    NO_SUCH_AIRPORT = "no_such_airport"
    NO_SUCH_CITY = "no_such_city"
    SAME_PLACE = "same_place"
    NO_FLIGHT = "no_flight"
    NO_ROUTE = "no_route"


class PlaceKind(Enum):
    AIRPORT = "airport"
    CITY = "city"


class Direction(Enum):
    FORWARD = "forward"
    BACKWARD = "backward"


PLACE = (
    "Three-letter uppercase IATA code (HOU), city (Houston), or city and country (Portland, United States). "
    "City matching ignores case and accents."
)
CODE = "An airport's IATA code, three capital letters"
STATUS = (
    "found: valid route; no_such_airport: unknown IATA code; no_such_city: unknown city; "
    "same_place: origin and destination share an airport; no_flight: all origins lack outgoing flights or "
    "all destinations lack incoming flights; no_route: flights exist but no route connects the places. "
    "Origin lookup errors take precedence over destination errors."
)


@dataclass
class RouteInput(Output):
    origin: Annotated[str, "Starting place: IATA code, city, or city and country"]
    destination: Annotated[str, "Destination: IATA code, city, or city and country"]


@dataclass
class RouteOutput(Output):
    status: Annotated[Status, STATUS]
    airports: Annotated[
        list[str],
        "IATA codes from origin to destination, without repeats and with a flight between each pair; empty unless found",
    ]


@dataclass
class PlaceInput(Output):
    place: Annotated[str, PLACE]


@dataclass
class Airport(Output):
    code: Annotated[str, CODE]
    city: Annotated[str, "Its city, as the data writes it; empty when the data has none"]
    country: Annotated[str, "Its country"]
    flights_out: Annotated[int, "How many airports it has a flight to"]
    flights_in: Annotated[int, "How many airports have a flight to it"]


@dataclass
class PlaceOutput(Output):
    place: Annotated[str, "The place asked for, unchanged"]
    kind: Annotated[PlaceKind, "airport: the place was read as an IATA code; city: as a city name"]
    airports: Annotated[list[Airport], "Every airport the place names, sorted by code; never empty"]


@dataclass
class NextInput(Output):
    airports: Annotated[list[str], "IATA codes of airports, each once: 1 or more"]
    direction: Annotated[
        Direction,
        "forward: the airports these have a flight to; backward: the airports that have a flight to these",
    ]


@dataclass
class Reached(Output):
    airport: Annotated[str, "An airport reached, as an IATA code: never one of the airports asked about"]
    via: Annotated[
        str,
        "The airport asked about it was reached from, the first by code if several: forward, via flies to airport; "
        "backward, airport flies to via",
    ]


@dataclass
class NextOutput(Output):
    reached: Annotated[
        list[Reached],
        "Every airport one flight away in the direction asked, each once, sorted by airport; empty when none",
    ]


TOOLS = {
    Tool.FIND_AIRPORTS: (PlaceInput, PlaceOutput),
    Tool.NEXT_AIRPORTS: (NextInput, NextOutput),
}
TASKS = {Task.PLAN_FLIGHT_ROUTE: (RouteInput, RouteOutput)}
