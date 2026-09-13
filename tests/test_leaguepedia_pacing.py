"""No real sleeping or network: validate pages, probes and bounded backoff."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from jobs.leaguepedia import client as cargo


class APIError(Exception):
    def __init__(self, code):
        self.code = code


@pytest.fixture
def clock(monkeypatch):
    state = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        state[0] += seconds

    monkeypatch.setattr(cargo.time, "monotonic", lambda: state[0])
    monkeypatch.setattr(cargo.time, "sleep", sleep)
    monkeypatch.setattr(cargo, "_next_cargo_at", 0.0)
    return sleeps


def test_pages_and_probe_are_paced(clock):
    query = Mock(side_effect=[[{"id": 1}], [{"id": 2}], []])
    client = SimpleNamespace(cargo_client=SimpleNamespace(query=query))
    assert len(cargo.cargo_query(client, "Games", "id", page_size=1, max_pages=2, strict=True)) == 2
    assert clock == [2.0, 2.0]
    assert query.call_args.kwargs["offset"] == 2


def test_non_strict_queries_share_pacing(clock):
    client = SimpleNamespace(cargo_client=SimpleNamespace(query=Mock(return_value=[])))
    cargo.cargo_query(client, "Teams", "Name")
    cargo.cargo_query(client, "Players", "Name")
    assert clock == [2.0]


def test_rate_limit_retries_same_page(clock):
    query = Mock(side_effect=[APIError("ratelimited"), APIError("ratelimited"), []])
    client = SimpleNamespace(cargo_client=SimpleNamespace(query=query))
    assert cargo.cargo_query(client, "Games", "id") == []
    assert clock == [60.0, 120.0]
    assert all(c.kwargs["offset"] == 0 for c in query.call_args_list)


def test_exhausted_retries_raise(clock):
    query = Mock(side_effect=APIError("ratelimited"))
    client = SimpleNamespace(cargo_client=SimpleNamespace(query=query))
    with pytest.raises(APIError):
        cargo.cargo_query(client, "Games", "id")
    assert query.call_count == 4
    assert clock == [60.0, 120.0, 240.0]


def test_other_errors_are_not_retried(clock):
    query = Mock(side_effect=APIError("badquery"))
    client = SimpleNamespace(cargo_client=SimpleNamespace(query=query))
    with pytest.raises(APIError):
        cargo.cargo_query(client, "Games", "id")
    assert query.call_count == 1
    assert clock == []
