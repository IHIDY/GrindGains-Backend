import asyncio
from zoneinfo import ZoneInfo

import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from grindgains_mcp import training
from grindgains_mcp.errors import ApiError, GrindGainsError, ReLoginRequiredError
from grindgains_mcp.server import create_server

HALIFAX = ZoneInfo("America/Halifax")


def row(movement_id="pushup", timestamp="2026-09-07T18:41:00.067781Z", mode="isotonic", weight=0, value=20, sets=3, rpe=8):
    item = {
        "movement_id": movement_id,
        "timestamp": timestamp,
        "mode": mode,
        "weight": weight,
        "reps_or_time": value,
        "sets": sets,
    }
    if rpe is not None:
        item["rpe"] = rpe
    return item


class FakeApi:
    def __init__(self, latest=None, histories=None, error=None):
        self.latest = latest or []
        self.histories = histories or {}
        self.error = error
        self.history_calls = []

    def list_movements(self):
        if self.error:
            raise self.error
        return self.latest

    def get_movement_history(self, movement_id):
        self.history_calls.append(movement_id)
        if self.error:
            raise self.error
        return self.histories[movement_id]


def call(api, name, arguments=None, zone=HALIFAX):
    server = create_server(lambda: api, zone)
    return asyncio.run(server.call_tool(name, arguments or {}))


def result_rows(result):
    return result.structured_content["result"]


def test_list_movements_summarizes_each_movement_most_recent_first():
    api = FakeApi(
        latest=[row("plank", mode="mobeta"), row("bench_press")],
        histories={
            "plank": [row("plank", "2026-09-05T12:00:00Z", "mobeta", 10, 45, 1, None)],
            "bench_press": [
                row("bench_press", "2026-09-07T18:41:00Z", weight=185, value=5, sets=1),
                row("bench_press", "2026-09-01T18:41:00Z", weight=175, value=5, sets=1),
            ],
        },
    )

    rows = result_rows(call(api, "list_movements"))

    assert rows == [
        {
            "movement_id": "bench_press",
            "display_name": "Bench Press",
            "mode": "isotonic",
            "entry_count": 2,
            "last_logged_date_local": "2026-09-07",
        },
        {
            "movement_id": "plank",
            "display_name": "Plank",
            "mode": "mobeta",
            "entry_count": 1,
            "last_logged_date_local": "2026-09-05",
        },
    ]


def test_history_has_explicit_units_and_splits_reps_from_hold_seconds():
    api = FakeApi(
        histories={
            "pushup": [row("pushup", weight=25, value=12, sets=3, rpe=8)],
            "plank": [row("plank", mode="mobeta", weight=10, value=45, sets=1, rpe=None)],
        }
    )

    [isotonic] = result_rows(call(api, "get_movement_history", {"movement_id": "pushup"}))
    [hold] = result_rows(call(api, "get_movement_history", {"movement_id": "plank"}))

    assert isotonic["weight_lb"] == 25
    assert isotonic["reps"] == 12 and isotonic["hold_seconds"] is None
    assert isotonic["sets"] == 3 and isotonic["rpe"] == 8
    assert hold["weight_lb"] == 10
    assert hold["hold_seconds"] == 45 and hold["reps"] is None
    assert hold["rpe"] is None


def test_history_is_oldest_first_even_if_the_api_order_differs():
    api = FakeApi(
        histories={
            "pushup": [
                row(timestamp="2026-09-09T12:00:00Z"),
                row(timestamp="2026-09-07T12:00:00Z"),
                row(timestamp="2026-09-08T12:00:00Z"),
            ]
        }
    )

    rows = result_rows(call(api, "get_movement_history", {"movement_id": "pushup"}))

    assert [r["date_local"] for r in rows] == ["2026-09-07", "2026-09-08", "2026-09-09"]


def test_a_late_evening_entry_maps_to_the_correct_local_date():
    # 01:30 UTC on Sep 8 is 22:30 on Sep 7 in Halifax (ADT, UTC-3).
    api = FakeApi(histories={"pushup": [row(timestamp="2026-09-08T01:30:00Z")]})

    [entry] = result_rows(call(api, "get_movement_history", {"movement_id": "pushup"}))

    assert entry["date_local"] == "2026-09-07"
    assert entry["timestamp"] == "2026-09-07T22:30:00-03:00"


def test_the_local_offset_follows_daylight_saving():
    api = FakeApi(histories={"pushup": [row(timestamp="2026-01-15T03:30:00Z")]})

    [entry] = result_rows(call(api, "get_movement_history", {"movement_id": "pushup"}))

    assert entry["date_local"] == "2026-01-14"
    assert entry["timestamp"] == "2026-01-14T23:30:00-04:00"


def test_the_timezone_is_configurable():
    api = FakeApi(histories={"pushup": [row(timestamp="2026-09-08T01:30:00Z")]})

    [entry] = result_rows(call(api, "get_movement_history", {"movement_id": "pushup"}, zone=ZoneInfo("UTC")))

    assert entry["date_local"] == "2026-09-08"


def test_timezone_defaults_to_halifax_and_reads_the_environment(monkeypatch):
    monkeypatch.delenv("GRINDGAINS_TZ", raising=False)
    assert training.get_timezone().key == "America/Halifax"

    monkeypatch.setenv("GRINDGAINS_TZ", "America/Vancouver")
    assert training.get_timezone().key == "America/Vancouver"


def test_an_unknown_timezone_is_a_clear_error():
    with pytest.raises(GrindGainsError, match="GRINDGAINS_TZ"):
        training.get_timezone("Mars/Olympus")


@pytest.mark.parametrize("bad_id", ["", "bench/press", "bench press", "x" * 129, "a#b"])
def test_an_invalid_movement_id_is_rejected_before_any_request(bad_id):
    api = FakeApi(histories={})

    with pytest.raises(ToolError, match="movement_id must be 1-128 characters") as excinfo:
        call(api, "get_movement_history", {"movement_id": bad_id})

    assert not isinstance(excinfo.value, UnexpectedToolError)
    assert api.history_calls == []


@pytest.mark.parametrize(
    "error",
    [
        ReLoginRequiredError("The saved login expired or was revoked. Run: python -m grindgains_mcp.login ..."),
        ApiError("The API returned an error (HTTP 500): Internal error"),
    ],
)
@pytest.mark.parametrize("tool,arguments", [("list_movements", {}), ("get_movement_history", {"movement_id": "pushup"})])
def test_backend_and_login_errors_become_clear_tool_errors(error, tool, arguments):
    with pytest.raises(ToolError) as excinfo:
        call(FakeApi(error=error), tool, arguments)

    assert not isinstance(excinfo.value, UnexpectedToolError)
    assert str(error) in str(excinfo.value)


def test_unexpected_exceptions_do_not_leak_their_details():
    api = FakeApi(error=RuntimeError("Bearer eyJ-secret-token"))

    with pytest.raises(UnexpectedToolError) as excinfo:
        call(api, "list_movements")

    assert "secret" not in str(excinfo.value)


def test_every_tool_is_read_only_and_there_are_no_write_tools():
    server = create_server(lambda: FakeApi(), HALIFAX)

    tools = asyncio.run(server.list_tools())

    assert {t.name for t in tools} == {"list_movements", "get_movement_history"}
    for tool in tools:
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
