# GrindGains Backend

![CI](https://github.com/IHIDY/GrindGains-Backend/actions/workflows/ci.yml/badge.svg)

"What Gets Measured gets managed" - V.F. Ridgway, 1956.



[Live app](https://grindgains.junfa-li.me) · [Frontend repo](https://github.com/IHIDY/GrindGains-Frontend) · [Ask Claude about your training](mcp-server/)

## How it works

![Architecture diagram: the web app and the MCP server call one Lambda with a Cognito ID token, the Lambda reads and writes one DynamoDB table, and sign-up goes through Cognito and a second Lambda that checks the invite code](docs/architecture.svg)

## Why it looks like this

**No API Gateway, so the Lambda checks the token itself.** A Function URL adds no cost on top of the Lambda. Without API Gateway there is no built-in Cognito authorizer, so `src/auth.py` verifies the signature, issuer, audience and expiry on every request and rejects anything that is not an ID token. The catch is that nothing throttles requests for me, so there is no rate limiting yet.

**One DynamoDB table, one partition per user.** Keys look like `USER#<sub>` and `MOVEMENT#<id>#LOG#<time>`, so a user can only ever read their own partition. You pay per request instead of for idle capacity. The catch is that listing every movement reads all of a user's logs, which is fine for a personal log and needs pagination if it grows.

**Invite only, enforced at sign-up.** A Cognito Pre Sign-up Lambda spends a one-time code and claims the username in a single transaction, so two people can't race for the same code. It is its own function because CloudFormation rejects the circular dependency between the user pool and the function.

**Least privilege per function.** The API function is allowed only `PutItem` and `Query` on the one table. The sign-up function is allowed only `UpdateItem` and `PutItem`, and its code only touches invite and username items.

## How it was built

![Workflow diagram: discuss, write an issue, code on a branch, open a pull request, CI, squash merge, with a context box, a red-CI loop, an undo path and a docs-only exception](docs/ai-workflow.svg)

This project is built with Claude Code, and every change follows the same loop. The idea is talked through first, then written up as an issue with a goal and acceptance criteria that a test can prove. The work happens on its own branch with the tests in the same pull request, and the pull request ticks off each criterion with its evidence. CI has to be green before a squash merge, so each issue is one commit that can be reverted on its own.

Every session starts by reading the same context files, so a fresh agent knows the spec, the process and how to test. Criteria that need a real account, such as signing in through Claude Desktop, stay unticked and keep the issue open until they are done. README and other prose edits skip the loop and go straight to `main`. The full rules are in [`_docs/process.md`](_docs/process.md).

## Documentation

- [API and data model](docs/api.md): every endpoint, field and error
- [Authentication and sign-up](docs/auth.md): token checks, invite codes, usernames, calling the API from a client
- [Deploying and running your own](docs/deploy.md): the stack, deploy steps, invite codes, permissions
- [MCP server](mcp-server/README.md): let Claude read your training log

Working on this repo with an AI agent? Start with [AGENTS.md](AGENTS.md).

## Known gaps

- No rate limiting on the Function URL. Fine at personal scale, but a script could flood it.
- No pagination. Listing every movement reads all of a user's logs, so it is the first call to watch as history grows.
- No password reset in the web app yet.
- The tests do not cover `src/auth.py` or the sign-up trigger yet.
