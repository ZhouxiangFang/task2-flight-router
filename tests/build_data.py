"""Builds verifier/data.py from the frozen OpenFlights snapshot in tests/openflights/.

    uv run python tests/build_data.py

The snapshot is airports.dat and routes.dat from https://github.com/jpatokal/openflights at commit COMMIT, checked
against SHA256 before anything is read. The rules:

- An airport is a row of airports.dat with an IATA code of three capital letters (which leaves out "\\N" and DU9, a
  Canadian field with no flights); its city and country are kept as written ("\\N" becomes an empty city, which no
  city name finds).
- A flight is a row of routes.dat with no stops, between two different airports that airports.dat has; the airline
  is dropped, so a flight is a pair of airports, and the pair is kept once however many airlines fly it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
SNAPSHOT = HERE / "openflights"
TARGET = HERE.parent / "verifier" / "data.py"
COMMIT = "e539814f664cf31e662710555b27e9688610a911"
SHA256 = {
    "airports.dat": "9387cdb38df5bd664da823f8ccb69fdd9b33a1888f5b7cca09c34a3cd9ff59f9",
    "routes.dat": "bd373706238134f619c624c606dccc74c05c2582a977c489c81de501735f2390",
}
MISSING = "\\N"


def read_snapshot(name: str) -> list[list[str]]:
    data = (SNAPSHOT / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA256[name]:
        raise SystemExit(f"tests/openflights/{name} is not the pinned snapshot: its SHA-256 differs")
    return list(csv.reader(data.decode("utf-8").splitlines()))


def build() -> tuple[dict[str, tuple[str, str]], dict[str, list[str]]]:
    """Every airport, code -> (city, country), and every airport's flights, code -> the codes it flies to."""
    airports = {}
    for row in read_snapshot("airports.dat"):
        code, city, country = row[4], row[2], row[3]
        if re.fullmatch(r"[A-Z]{3}", code):
            airports[code] = ("" if city == MISSING else city, country)
    flights: dict[str, set[str]] = {}
    for row in read_snapshot("routes.dat"):
        origin, destination, stops = row[2], row[4], row[7]
        if stops == "0" and origin != destination and origin in airports and destination in airports:
            flights.setdefault(origin, set()).add(destination)
    return dict(sorted(airports.items())), {code: sorted(flights[code]) for code in sorted(flights)}


def quoted(text: str) -> str:
    """``text`` as a double-quoted Python string, the way ruff formats one."""
    return json.dumps(text, ensure_ascii=False)


def render(airports: dict[str, tuple[str, str]], flights: dict[str, list[str]]) -> str:
    count = sum(map(len, flights.values()))
    lines = [
        '"""The airports and the nonstop flights between them: a frozen OpenFlights snapshot, built by',
        "tests/build_data.py from tests/openflights/ (commit " + COMMIT[:12] + ", ODbL), which says how.",
        "",
        "This is the one copy of the data. The plugin's tools read it, and the verifier judges every tool output and every",
        "answer against it, so no verdict trusts what a tool returned.",
        "",
        f'{len(airports)} airports, {len(flights)} of them with flights out; {count} flights."""',
        "",
        "# code -> (city, country), as airports.dat writes them; an empty city is none",
        "AIRPORTS = {",
        *(f"    {quoted(code)}: ({quoted(city)}, {quoted(country)})," for code, (city, country) in airports.items()),
        "}",
        "",
        "# code -> the codes of the airports it has a nonstop flight to, space-separated and sorted",
        "FLIGHTS = {",
        *(f"    {quoted(code)}: {quoted(' '.join(destinations))}," for code, destinations in flights.items()),
        "}",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    TARGET.write_text(render(*build()), encoding="utf-8")
    print(f"wrote {TARGET}")
