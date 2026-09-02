"""
TrainingGPT MVP backend — single Lambda behind a Function URL, routing on
HTTP method, backed by a single DynamoDB table (single-table design).

PK: USER#<user_id>            (hardcoded to USER#ME for this MVP)
SK: MOVEMENT#<movement_id>#LOG#<timestamp_iso8601>

POST -> log a new set/hold.
GET  -> list all logs for a given movement_id.

CORS is handled entirely by the Lambda Function URL's Cors config (see
template.yaml) — AWS answers OPTIONS preflight requests directly without
invoking this function, so no CORS headers are added here.
"""

import datetime
import decimal
import json
import os

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ["TABLE_NAME"]
USER_ID = "ME"  # hardcoded single user for the MVP

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME)

VALID_MODES = ("isotonic", "mobeta")


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")

    try:
        if method == "POST":
            return _handle_post(event)
        if method == "GET":
            return _handle_get(event)
        return _response(405, {"error": f"Unsupported method: {method}"})
    except ValueError as exc:
        return _response(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - MVP: surface a generic 500
        return _response(500, {"error": "Internal error", "detail": str(exc)})


def _handle_post(event):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc

    movement_id = body.get("movement_id")
    mode = body.get("mode")
    weight = body.get("weight")
    reps_or_time = body.get("reps_or_time")
    sets = body.get("sets", 1)  # defaults to 1 (always, incl. mobeta holds)

    missing = [
        field
        for field, value in (
            ("movement_id", movement_id),
            ("mode", mode),
            ("weight", weight),
            ("reps_or_time", reps_or_time),
        )
        if value is None
    ]
    if missing:
        raise ValueError(f"Missing required field(s): {', '.join(missing)}")
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )

    item = {
        "PK": f"USER#{USER_ID}",
        "SK": f"MOVEMENT#{movement_id}#LOG#{timestamp}",
        "mode": mode,
        "weight": _to_decimal(weight),
        "reps_or_time": _to_decimal(reps_or_time),
        "sets": _to_decimal(sets),
    }

    _table.put_item(Item=item)
    return _response(201, item)


def _handle_get(event):
    params = event.get("queryStringParameters") or {}
    movement_id = params.get("movement_id")
    if not movement_id:
        raise ValueError("movement_id query parameter is required")

    sk_prefix = f"MOVEMENT#{movement_id}#LOG#"
    result = _table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{USER_ID}")
        & Key("SK").begins_with(sk_prefix)
    )
    return _response(200, result.get("Items", []))


def _to_decimal(value):
    # DynamoDB's boto3 client requires Decimal, not float, for Number types.
    return decimal.Decimal(str(value))


def _json_default(obj):
    if isinstance(obj, decimal.Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }
