"""results/map.json must match the published schema.

The schema is the contract for anyone consuming the map without reading prose. A
schema nobody checks is documentation, and documentation drifts.
"""
import json
import os

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_map_matches_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.load(open(os.path.join(HERE, "schemas", "map.schema.json")))
    jsonschema.Draft202012Validator.check_schema(schema)
    path = os.path.join(HERE, "results", "map.json")
    if not os.path.exists(path):
        pytest.skip("no map yet; run ./run.sh")
    jsonschema.Draft202012Validator(schema).validate(json.load(open(path)))


def test_every_case_carries_a_clause():
    import sys
    sys.path.insert(0, os.path.join(HERE, "src"))
    from suite_all import CASES
    missing = [c.id for c in CASES if not c.clause.strip()]
    assert not missing, f"cases with no clause: {missing}"


def test_every_case_has_a_reference_answer_or_says_why():
    """A construct with no computable reference is not a conformance test, unless the
    case is scored on whether the engine accepts or refuses it.

    Two kinds have no reference and are still tests. A REJECT case is ill-formed, so
    there is nothing for a conforming engine to return. An ACCEPT control can be
    well-formed and still have an infinite admissible set -- an unbounded quantifier
    under WALK with ANY -- so acceptance is the whole test. Anything else with no
    reference is a query nobody can grade, and should not be in the suite.
    """
    import sys
    sys.path.insert(0, os.path.join(HERE, "src"))
    import fixtures
    from gpml_ref import match
    from suite_all import CASES
    for c in CASES:
        try:
            match(fixtures.FIXTURES[c.fixture](), c.ref)
        except ValueError:
            assert c.expect in ("ACCEPT", "REJECT"), (
                f"{c.id} has no reference answer and is not scored on acceptance "
                f"or refusal, so nothing can grade it")
