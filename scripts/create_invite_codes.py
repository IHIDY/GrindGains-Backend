#!/usr/bin/env python3
"""
Generate one-time invite codes and write them into the TrainingLogs table
(as PK=INVITECODE#<code>, SK=STATUS, unused). Run this locally with AWS
credentials that can PutItem on the table — e.g. the same credentials you
used to `sam deploy`. Each printed code works for exactly one sign-up.

Usage:
  python3 scripts/create_invite_codes.py --count 5
  python3 scripts/create_invite_codes.py --count 5 --table TrainingLogs --region ca-central-1
"""

import argparse
import secrets
import string

import boto3

ALPHABET = string.ascii_uppercase + string.digits


def generate_code(length=8):
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default="TrainingLogs")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--region", default=None)
    args = parser.parse_args()

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)

    for _ in range(args.count):
        code = generate_code()
        table.put_item(
            Item={"PK": f"INVITECODE#{code}", "SK": "STATUS"},
            ConditionExpression="attribute_not_exists(PK)",
        )
        print(code)


if __name__ == "__main__":
    main()
