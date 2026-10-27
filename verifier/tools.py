"""The tool calls' checks: every list of codes is well formed, and each output is exactly what the data says."""

from contract import Tool

from .checks import AIRPORTS, ARRIVALS, DEPARTURES, codes_problem, next_reached, resolve, result


def verify_input(tool, value):
    # Any place may be asked for, and any well-formed code: the tool itself says when it names nothing.
    if tool is Tool.NEXT_AIRPORTS:
        problem = codes_problem(value.airports)
        if problem:
            return result(False, problem, given=value.airports)
    return result(True, "input is valid")


def verify_output(tool, input_value, output_value, workspace):
    if tool is Tool.FIND_AIRPORTS:
        return verify_place(input_value.place, output_value)
    unknown = sorted(code for code in input_value.airports if code not in AIRPORTS)
    if unknown:
        return result(False, f"no airport has the code(s) {unknown}, so the tool must fail, not answer")
    expected = list(next_reached(input_value.airports, input_value.direction).items())
    given = [(entry.airport, entry.via) for entry in output_value.reached]
    if given != expected:
        return result(False, "next_airports must give exactly what the data says", expected=expected, given=given)
    return result(True, "output is valid")


def verify_place(place, output_value):
    kind, codes = resolve(place)
    if not codes:
        return result(False, f"{place!r} names no {kind.value}, so the tool must fail, not answer")
    expected = [(code, *AIRPORTS[code], len(DEPARTURES.get(code, [])), len(ARRIVALS.get(code, []))) for code in codes]
    given = [
        (airport.code, airport.city, airport.country, airport.flights_out, airport.flights_in)
        for airport in output_value.airports
    ]
    if output_value.place != place or output_value.kind is not kind or given != expected:
        return result(False, f"{place!r} names the {kind.value} airports {codes}", expected=expected, given=given)
    return result(True, "output is valid")
