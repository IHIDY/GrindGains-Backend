"""
TrainingGPT MVP backend — single Lambda behind a Function URL, routing on
HTTP method, backed by a single DynamoDB table (single-table design).

PK: USER#<user_id>            (user_id = the caller's Cognito `sub`)
SK: MOVEMENT#<movement_id>#LOG#<timestamp_iso8601>

POST -> log a new set/hold.
GET  -> list all logs for a given movement_id.

Every request must carry a Cognito ID token (`Authorization: Bearer <jwt>`),
verified in auth.py — there's no shared secret and no per-user config here,
each user is scoped to their own token's `sub`.

CORS is handled entirely by the Lambda Function URL's Cors config (see
template.yaml) — AWS answers OPTIONS preflight requests directly without
invoking this function, so no CORS headers are added here.
"""

import datetime
import decimal
import json
import logging
import os
import re

import boto3
from boto3.dynamodb.conditions import Key

from auth import get_authenticated_user_id

TABLE_NAME = os.environ["TABLE_NAME"]

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME)

VALID_MODES = ("isotonic", "mobeta")
MOVEMENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")

    user_id = get_authenticated_user_id(event)
    if user_id is None:
        return _response(401, {"error": "Unauthorized"})

    try:
        if method == "POST":
            return _handle_post(event, user_id)
        if method == "GET":
            return _handle_get(event, user_id)
        return _response(405, {"error": f"Unsupported method: {method}"})
    except ValueError as exc:
        return _response(400, {"error": str(exc)})
    except Exception:  # noqa: BLE001 - MVP: surface a generic 500
        # Full detail goes to CloudWatch only; callers never see internal
        # exception text (could otherwise leak boto3/DynamoDB internals).
        logger.exception("Unhandled error processing request")
        return _response(500, {"error": "Internal error"})


def _handle_post(event, user_id):
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

    movement_id = _validate_movement_id(movement_id)
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")
    weight = _validate_number("weight", weight)
    reps_or_time = _validate_number("reps_or_time", reps_or_time)
    sets = _validate_number("sets", sets)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )

    item = {
        "PK": f"USER#{user_id}",
        "SK": f"MOVEMENT#{movement_id}#LOG#{timestamp}",
        "mode": mode,
        "weight": _to_decimal(weight),
        "reps_or_time": _to_decimal(reps_or_time),
        "sets": _to_decimal(sets),
    }

    _table.put_item(Item=item)
    return _response(201, item)


def _handle_get(event, user_id):
    params = event.get("queryStringParameters") or {}
    movement_id = params.get("movement_id")
    if not movement_id:
        raise ValueError("movement_id query parameter is required")
    movement_id = _validate_movement_id(movement_id)

    sk_prefix = f"MOVEMENT#{movement_id}#LOG#"
    result = _table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}")
        & Key("SK").begins_with(sk_prefix)
    )
    return _response(200, result.get("Items", []))


def _validate_movement_id(movement_id):
    if not isinstance(movement_id, str) or not MOVEMENT_ID_RE.match(movement_id):
        raise ValueError(
            "movement_id must be 1-128 characters: letters, digits, "
            "underscore, or hyphen"
        )
    return movement_id


def _validate_number(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {type(value).__name__}")
    return value


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
