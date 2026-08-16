"""Data migrations must name their connection (D-170).

This project runs migrations on the `admin` alias, because the default
connection is the deliberately under-privileged RLS role and cannot alter
tables. A bare `.objects` query inside `RunPython` therefore uses a DIFFERENT,
second connection - and if the migration has taken a lock, that second
connection waits for a lock its own migration is holding.

It does not error. It hangs, forever, and only when the migration has rows to
touch. In production it presented as an SSH failure during deploy: the ALTER sat
idle in transaction for over an hour, the table was left without its RLS policy,
and one workspace silently lost its assistant instructions.

The fix is one line per query - `.using(schema_editor.connection.alias)` - and
this test exists because nothing else would catch the next one. An empty
development database hides it completely.
"""

import ast
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[3]

# Names that read or write rows. A migration touching any of these without
# naming a connection is the shape that deadlocks.
QUERY_ATTRS = {"objects", "all_objects"}


def migration_files():
    return sorted(BACKEND.glob("apps/*/migrations/*.py"))


def runpython_functions(tree):
    """Names passed to RunPython, forward and reverse."""
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = getattr(func, "attr", None) or getattr(func, "id", None)
        if called != "RunPython":
            continue
        for argument in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(argument, ast.Name):
                names.add(argument.id)
    return names


def bare_queries(function: ast.FunctionDef) -> list[str]:
    """`Model.objects.<something>` not wrapped in `.using(...)`.

    Walks upward from the `.objects` attribute: a queryset is only safe if
    `using` appears somewhere in the chain built on top of it.
    """
    offenders = []

    for node in ast.walk(function):
        if not (isinstance(node, ast.Attribute) and node.attr in QUERY_ATTRS):
            continue

        # Find the outermost expression built on this `.objects`.
        chain = []
        for candidate in ast.walk(function):
            if isinstance(candidate, ast.Call) and _contains(candidate, node):
                chain.append(candidate)

        if not any(
            isinstance(call.func, ast.Attribute) and call.func.attr == "using" for call in chain
        ):
            offenders.append(f"line {node.lineno}: .{node.attr} without .using()")

    return offenders


def _contains(outer: ast.AST, inner: ast.AST) -> bool:
    return any(child is inner for child in ast.walk(outer))


@pytest.mark.parametrize(
    "path", migration_files(), ids=lambda p: f"{p.parent.parent.name}/{p.name}"
)
def test_data_migrations_name_their_connection(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    targets = runpython_functions(tree)
    if not targets:
        return

    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in targets:
            problems += [f"{node.name}() {issue}" for issue in bare_queries(node)]

    assert not problems, (
        f"{path.name} runs queries on the default connection inside RunPython:\n  "
        + "\n  ".join(problems)
        + "\n\nUse .using(schema_editor.connection.alias). Migrations run on the "
        "`admin` alias; a default-connection query waits on a lock its own "
        "migration holds and hangs forever."
    )
