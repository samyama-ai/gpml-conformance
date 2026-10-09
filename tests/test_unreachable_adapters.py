"""An adapter whose engine is not running must refuse to construct, and quickly.

`build_engines` leaves an engine out of the run only when its constructor raises.
Grafeo's and ArcadeDB's constructors used to succeed against a dead port, so both
joined every run where they were absent. Grafeo's `load` then waited a minute per
case for an engine that was never coming: 84 cases, 84 minutes, and the
samyama-graph conformance job was cancelled at its 45-minute limit on every run.
"""
import os
import socket
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

pytest.importorskip("requests")

from engines_adapters import ArcadeAdapter, EngineUnavailable, GrafeoAdapter  # noqa: E402


def _dead_url() -> str:
    """A localhost URL with nothing listening on it."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}"


@pytest.mark.parametrize("make", [
    lambda url: GrafeoAdapter(base=url),
    lambda url: ArcadeAdapter(base=url),
], ids=["grafeo", "arcadedb"])
def test_an_absent_engine_refuses_to_construct_within_seconds(make):
    t0 = time.monotonic()
    with pytest.raises(EngineUnavailable):
        make(_dead_url())
    assert time.monotonic() - t0 < 5, "an absent engine must be refused, not waited for"
