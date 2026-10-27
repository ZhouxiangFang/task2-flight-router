"""The plan-flight-route task's check: any route of real flights passes, however many it takes: not one fixed
answer and not only the shortest."""

from contract import Status

from .checks import expected, fewest_legs, result, route_problem


def verify_task(arguments, output, reference, workspace):
    """``output``: a contract RouteOutput, judged against the data itself (the task has no reference tool)."""
    status, fact, origins, destinations = expected(arguments.origin, arguments.destination)
    if output.status is not status:
        return result(False, f"{fact}, so the status is {status.value}, but the answer says {output.status.value}")
    if status is not Status.FOUND:
        if output.airports:
            return result(False, "airports must be empty unless status is found", airports=output.airports)
        return result(True, f"{fact}, as the answer says")
    problem = route_problem(output.airports, origins, destinations)
    if problem:
        score = problem.pop("score", 0.0)
        return result(False, problem.pop("message"), score=score, **problem)
    legs = len(output.airports) - 1
    fewest = fewest_legs(origins, destinations)
    return result(True, f"a route of {legs} real flight(s); the fewest is {fewest}", airports=output.airports)
