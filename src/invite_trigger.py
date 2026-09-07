"""
Cognito Pre Sign-up trigger — gates registration behind a one-time invite
code, and (if the sign-up includes a `preferred_username`) enforces that
usernames are unique.

Deliberately separate from app.py / auth.py: this function only needs
TABLE_NAME. It must NOT depend on USER_POOL_ID, because the User Pool's
LambdaConfig has to reference this function's ARN — if this function also
referenced the User Pool back (like app.py does, to verify JWTs), the two
resources would form a circular dependency and CloudFormation would refuse
to deploy the stack.

Invite codes and claimed usernames live in the same TrainingLogs table
(single-table design):
  PK = INVITECODE#<code>,          SK = STATUS
  PK = USERNAME#<lowercased name>, SK = STATUS

Both checks happen in a single DynamoDB transaction (TransactWriteItems),
not two independent writes — if it were two separate calls, a sign-up could
claim the username and then fail the invite-code check (or vice versa),
permanently locking that username to an account that was never actually
created. The transaction makes both succeed or both roll back together.
"""

import datetime
import os

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["TABLE_NAME"]

_client = boto3.client("dynamodb")


def lambda_handler(event, context):
    request = event.get("request", {})
    client_metadata = request.get("clientMetadata") or {}
    user_attributes = request.get("userAttributes") or {}

    code = client_metadata.get("invite_code")
    if not code:
        # Raising rejects the SignUp call; Cognito surfaces the message to the caller.
        raise Exception("An invite code is required to sign up.")

    username = event.get("userName", "")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    transact_items = [
        {
            "Update": {
                "TableName": TABLE_NAME,
                "Key": {"PK": {"S": f"INVITECODE#{code}"}, "SK": {"S": "STATUS"}},
                "UpdateExpression": "SET used_by = :u, used_at = :t",
                "ConditionExpression": "attribute_exists(PK) AND attribute_not_exists(used_by)",
                "ExpressionAttributeValues": {
                    ":u": {"S": username},
                    ":t": {"S": now},
                },
            }
        }
    ]

    preferred_username = user_attributes.get("preferred_username")
    if preferred_username:
        transact_items.append(
            {
                "Put": {
                    "TableName": TABLE_NAME,
                    "Item": {
                        "PK": {"S": f"USERNAME#{preferred_username.lower()}"},
                        "SK": {"S": "STATUS"},
                        "claimed_by": {"S": username},
                        "claimed_at": {"S": now},
                    },
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            }
        )

    try:
        _client.transact_write_items(TransactItems=transact_items)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "TransactionCanceledException":
            reasons = exc.response.get("CancellationReasons", [])
            invite_failed = bool(reasons) and reasons[0].get("Code") == "ConditionalCheckFailed"
            username_failed = len(reasons) > 1 and reasons[1].get("Code") == "ConditionalCheckFailed"
            if invite_failed:
                raise Exception("Invalid or already-used invite code.") from exc
            if username_failed:
                raise Exception("That username is already taken.") from exc
        raise

    return event
