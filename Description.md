**Project Context:**
We are building the MVP backend for a personal training tracker that supports traditional sets/reps and isometric time-under-tension tracking. This backend must be extremely lightweight, serverless, and optimized for zero monthly cost. It will serve as the data foundation for a future AI Agent (via Model Context Protocol).

**Infrastructure as Code (IaC) & Stack:**
*   **IaC Tool:** AWS SAM (Serverless Application Model) or AWS CDK (Python).
*   **Runtime:** Python 3.11+
*   **Database:** Amazon DynamoDB (On-Demand Capacity to ensure $0 cost).
*   **Compute:** A single AWS Lambda function.
*   **API Exposure:** Use **Lambda Function URLs** (with CORS enabled for frontend access). **DO NOT** use API Gateway, as we want to avoid potential route costs.

**DynamoDB Single-Table Design:**
*   Table Name: `TrainingLogs`
*   **Partition Key (PK):** `String` (Format: `USER#<user_id>`. Hardcode to `USER#ME` for this MVP).
*   **Sort Key (SK):** `String` (Format: `MOVEMENT#<movement_id>#LOG#<timestamp_iso8601>`).
*   **Attributes:**
    *   `mode`: String (`isotonic` or `mobeta`).
    *   `weight`: Number (load in kg/lbs).
    *   `reps_or_time`: Number (represents repetitions for isotonic, or seconds for mobeta).
    *   `sets`: Number (default to 1 for mobeta).

**Lambda Router Logic:**
Since we are using a single Function URL, implement a basic HTTP method router inside the Python Lambda handler:
*   `POST`: Parse the JSON body, generate a UTC timestamp, construct the PK and SK, and `put_item` into DynamoDB.
*   `GET`: Extract `movement_id` from query parameters. Use DynamoDB `query` to fetch all items where PK is `USER#ME` and SK `begins_with(MOVEMENT#<movement_id>#LOG#)`. Return the items as a JSON array.

**Action Required:**
Please initialize the IaC project structure, write the database provisioning code, and implement the Python Lambda handler. Ensure the IAM role attached to the Lambda function strictly grants only `dynamodb:PutItem` and `dynamodb:Query` permissions for the specific table.