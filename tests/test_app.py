import decimal
import json
import os
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("TABLE_NAME", "fake-table")
os.environ.setdefault("AWS_REGION", "ca-central-1")
os.environ.setdefault("USER_POOL_ID", "fake-pool")
os.environ.setdefault("USER_POOL_CLIENT_ID", "fake-client")

with mock.patch("boto3.resource"):
    import app


@pytest.fixture
def fake_table():
    table = mock.MagicMock()
    with mock.patch.object(app, "_table", table):
        yield table


def _post(table, body, user_id="u1"):
    return app._handle_post({"body": json.dumps(body)}, user_id)


VALID_BODY = {
    "movement_id": "pushup",
    "mode": "isotonic",
    "weight": 100,
    "reps_or_time": 10,
}


def test_post_without_rpe_omits_it_from_item(fake_table):
    resp = _post(fake_table, VALID_BODY)
    assert resp["statusCode"] == 201
    item = fake_table.put_item.call_args[1]["Item"]
    assert "rpe" not in item
    assert json.loads(resp["body"])["rpe"] is None


def test_post_with_valid_rpe_stores_and_returns_it(fake_table):
    resp = _post(fake_table, {**VALID_BODY, "rpe": 8})
    assert resp["statusCode"] == 201
    item = fake_table.put_item.call_args[1]["Item"]
    assert item["rpe"] == decimal.Decimal("8")
    assert json.loads(resp["body"])["rpe"] == 8


@pytest.mark.parametrize("bad_rpe", [0, 11, -1, 10.5001 * 100])
def test_post_with_out_of_range_rpe_raises(fake_table, bad_rpe):
    with pytest.raises(ValueError):
        _post(fake_table, {**VALID_BODY, "rpe": bad_rpe})


def test_post_with_non_numeric_rpe_raises(fake_table):
    with pytest.raises(ValueError):
        _post(fake_table, {**VALID_BODY, "rpe": "hard"})


def test_post_missing_required_field_raises(fake_table):
    body = dict(VALID_BODY)
    del body["weight"]
    with pytest.raises(ValueError, match="weight"):
        _post(fake_table, body)


def test_get_handles_legacy_item_without_rpe(fake_table):
    fake_table.query.return_value = {
        "Items": [
            {
                "PK": "USER#u1",
                "SK": "MOVEMENT#pushup#LOG#2026-01-01T00:00:00.000000Z",
                "mode": "isotonic",
                "weight": decimal.Decimal("50"),
                "reps_or_time": decimal.Decimal("10"),
                "sets": decimal.Decimal("3"),
            }
        ]
    }
    resp = app._handle_get({"queryStringParameters": {"movement_id": "pushup"}}, "u1")
    assert resp["statusCode"] == 200
    [entry] = json.loads(resp["body"])
    assert entry["rpe"] is None
