# Flight Router

A `nanoagent.plugin/v0001` plugin. The agent is given an origin and a destination, each an airport's IATA code (such
as `HOU`) or a city (such as `Houston` or `Portland, United States`). It looks the places up in a frozen snapshot of
the public [OpenFlights](https://openflights.org/data) airport and route data, searches the flights between airports, and
returns every airport of a route between them, changing planes as often as it takes, or says why there is none. A
deterministic verifier, with no model, accepts any route of real flights. It does not need to be the shortest
route.

## Tools

| Tool | Does |
|---|---|
| `find_airports` | Gives every airport a place names, with each one's city, country and counts of flights out and in. It fails with "no such airport" or "no such city" when the place names nothing |
| `next_airports` | Takes one step of a breadth-first search. It gives every airport one flight away from some airports, `forward` (where they fly) or `backward` (what flies to them), each with the airport it was reached `via` |

| Task | Does |
|---|---|
| `plan-flight-route` | Finds a route of connecting flights from the origin to the destination, changing planes as often as it takes, or says why there is none. Runner `agent`, with both tools |

Input: `{"origin": "Houston", "destination": "London"}`.
Output: `{"status": "found", "airports": ["HOU", "ATL", "LHR"]}`, or another status with `"airports": []`.

### What a place names

- **An airport code** is exactly three capital letters, with any spaces around it dropped: `HOU`, `MAN`.
- **Anything else is a city name.** It matches whatever its case and accents: `houston`, `Sao Paulo` (São Paulo),
  `Vadso` (Vadsø). It names the city's airports in every country that has a city of that name. `London` names five
  airports in the United Kingdom, plus LOZ in the United States and YXU in Canada.
- **`City, Country` keeps only one country's airports.** It is read this way only when no city has the whole text as
  its name: `Portland, United States` gives PDX and PWM, while `Doncaster, Sheffield` is the name of one city (DSA).
- **A city is its `city` field in airports.dat.** Newark's EWR is the city Newark, so `New York` does not include it.

### Statuses: every edge case

The checks run in this order, and the first that holds decides the status:

| Status | When | Examples |
|---|---|---|
| `no_such_airport` | The origin, or else the destination, is three capital letters that no airport has | `ZZZ`, ` QQQ` |
| `no_such_city` | The origin, or else the destination, is any other text that no city has | `Atlantis`, `hou` (a code must be capitals), `HOUS`, `""`, `Portland, Canada`, `London UK` |
| `same_place` | An airport is both an origin and a destination | `London` to `LHR`; `Paris` to `Paris, France`; `Man` to `Man` |
| `no_flight` | No origin airport has a flight out, or no destination airport has a flight in. 2,814 of the 6,071 airports have no flights at all | `Man` (MJC) to `MAN`; `HOU` to `PTJ` (PTJ has flights out, none in) |
| `no_route` | There are flights, but no route of any length joins them | `GEA` to `CDG` (GEA flies only within New Caledonia); `CDG` to `GEA`; `Houston` to `Neerlerit Inaat` (CNP and OBY in Greenland fly only to each other) |
| `found` | A route exists | `Houston` to `Chicago` (1 flight); `HOU` to `London` (2); `AKN` to `TIA` (4); `YPO` to `IRP` (13, the longest shortest route in the data) |

Precedence follows the order of the checks. `Atlantis` to `ZZZ` is `no_such_city`, because the origin is checked
first, and `ZZZ` to `ZZZ` is `no_such_airport`, not `same_place`. A city can succeed where one of its airports fails:
`Noumea` to `Paris` is found through NOU, while `GEA` to `CDG` is `no_route`.

### How the verifier judges a route

For `found`, the verifier recomputes the status from the data and then checks `airports`:

| Answer | Verdict |
|---|---|
| Any route of real flights from an origin airport to a destination airport, however many | valid, score 1, even when it is not the shortest (`HOU`, `ATL`, `JFK`, `BOS`, `LHR` for `HOU` to `London`) |
| A connection through another airport of the origin's or destination's city | valid, if every flight is real |
| Fewer than two airports, or `[]` | invalid |
| An airport twice (a loop), a code no airport has, or a lowercase code | invalid |
| Starts outside the origin's airports, or ends outside the destination's (such as Portland, Australia for `Portland, United States`) | invalid |
| A flight that does not exist | invalid, with partial score: the share of the route's flights that do exist |
| The route flown backwards | invalid, since flights are one-way |
| The wrong status, or a non-empty `airports` with a status other than `found` | invalid |
| A malformed answer (a missing field, an unknown status, a string instead of a list, an extra field) | refused by NanoAgent before it reaches the verifier |

Every tool output is checked against the same data. A `next_airports` input must have at least one well-formed code,
each once. A well-formed code that no airport has passes the input check, and the tool itself then fails with "no such
airport".

### Keeping within the agent's limits

A route has no limit on its flights. The shortest route between two airports takes up to 13 flights (`YPO` to `IRP`).
`next_airports` is a stateless step of a breadth-first search, so the verifier checks each output from its input
alone. The task's instructions run that search from both ends:

1. Each turn, expand both frontiers in parallel while each has at most 10 airports. Otherwise expand only the
   smaller one.
2. Stop when the two searches meet, then rebuild the route from the `via`s.
3. If a frontier gives no new airport, everything reachable on that side has been searched, so submit `no_route`.

The tests play these instructions through the tools on 305 trips, and every answer earns a valid verdict. Measured
over 2,000 random airport pairs plus the hardest cases:

| | Median | Worst |
|---|---|---|
| Turns of `next_airports` | 2 | 7 (`YPO` to `IRP`) |
| Tool inputs and outputs the agent carries | | about 10k tokens |

Proving `no_route` stays cheap. For every one of the 193,354 airport pairs with no route, one side's search ends
within 100 airports.

This is the edge case where a route takes too long. A route needs about 1 + 7 + 1 model turns at worst: the lookup,
the search and the submit. If the run's step or token limit is lower than that, or the agent strays from the search,
it never submits and the run fails. The verifier itself has no limit. It recomputes the answer by breadth-first search
in milliseconds.

## Layout

```text
.
├── nanoagent.yaml        # manifest: tools, tasks, permissions
├── contract.py           # each tool's and task's typed input and output
├── src/plugin/           # the MCP server and the tools
├── verifier/             # the deterministic verifier; data.py is the airports and flights
├── tests/                # tests for the data, the tools and the verifier
│   ├── openflights/      # the frozen snapshot: airports.dat and routes.dat
│   └── build_data.py     # builds verifier/data.py from the snapshot
├── ui/                   # how results are drawn
└── product/              # the product page
```

## Develop and run

You need Git, [uv](https://docs.astral.sh/uv/) and Python 3.12 or later (uv fetches Python if needed). The plugin
needs no network access or API key at run time.

```bash
git clone https://github.com/ZhouxiangFang/task2-flight-router.git
cd task2-flight-router
uv sync --extra dev
uv run pytest
uv run ruff check .
```

To check the plugin against every NanoAgent publishing rule:

```bash
uvx --from "git+https://github.com/RUSH-LAB/nanoagent#subdirectory=nanoagent" nanoagent plugin inspect .
```

To rebuild `verifier/data.py` from the snapshot (a test checks that it matches):

```bash
uv run python tests/build_data.py
```

On RUSH Lab, open the plugin and ask its chat, for example, "Find flights from Houston to London". The result card
shows the verifier's verdict.

## Data

The data is `airports.dat` and `routes.dat` from
[jpatokal/openflights](https://github.com/jpatokal/openflights) at commit `e539814f664cf31e662710555b27e9688610a911`,
pinned in `tests/build_data.py` by SHA-256. It is made available under the
[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/). The plugin's code is MIT.
`build_data.py` keeps:

- each airport with an IATA code of three capital letters (6,071);
- each flight between two different airports that the airport file lists, dropping the 11 rows whose plane lands
  somewhere on the way (`stops` above 0), because the data does not say where. The airline is dropped too, so 37,041
  one-way flights remain out of 67,663 rows. A route changes planes at every airport between its two ends.

## Limitations

- OpenFlights stopped updating its routes in June 2014, so the flights are not today's. The task is about the
  snapshot, not the real world.
- A route counts flights only. It ignores schedules, connection times, airlines, distance and price.
- City names come from airports.dat as written. Letters with no accent to drop are folded only for a short list
  (`ø`, `æ`, `œ`, `đ`, `ð`, `þ`, `ł`, `ı`), so another spelling of a city may name nothing (`Malmö` is `Malmoe` in
  the data).
