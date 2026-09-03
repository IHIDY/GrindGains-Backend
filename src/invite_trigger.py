"""
Cognito Pre Sign-up trigger — gates registration behind a one-time invite
code.

Deliberately separate from app.py / auth.py: this function only needs
TABLE_NAME. It must NOT depend on USER_POOL_ID, because the User Pool's
LambdaConfig has to reference this function's ARN — if this function also
referenced the User Pool back (like app.py does, to verify JWTs), the two
resources would form a circular dependency and CloudFormation would refuse
to deploy the stack.

Invite codes live in the same TrainingLogs table (single-table design):
  PK = INVITECODE#<code>, SK = STATUS
created ahead of time via scripts/create_invite_codes.py. Consuming one is a
single conditional UpdateItem, so two sign-ups racing on the same code can't
both succeed — only one UpdateItem will pass the condition.
"""

import datetime
import os

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["TABLE_NAME"]

_table = boto3.resource("dynamodb").Table(TABLE_NAME)


def lambda_handler(event, context):
    client_metadata = event.get("request", {}).get("clientMetadata") or {}
    code = client_metadata.get("invite_code")
    if not code:
        # Raising rejects the SignUp call; Cognito surfaces the message to the caller.
        raise Exception("An invite code is required to sign up.")

    try:
        _table.update_item(
            Key={"PK": f"INVITECODE#{code}", "SK": "STATUS"},
            UpdateExpression="SET used_by = :u, used_at = :t",
            ConditionExpression="attribute_exists(PK) AND attribute_not_exists(used_by)",
            ExpressionAttributeValues={
                ":u": event.get("userName", ""),
                ":t": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise Exception("Invalid or already-used invite code.") from exc
        raise

    return event
