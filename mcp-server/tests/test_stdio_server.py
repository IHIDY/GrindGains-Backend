import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RUN_SERVER = Path(__file__).resolve().parents[1] / "run_server.py"


def run_against_real_server(tmp_path, scenario):
    """Start the real server as a subprocess speaking MCP over stdio and run `scenario(session)`."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(RUN_SERVER)],
        env={
            **os.environ,
            # No saved login: tools must fail clearly instead of touching the network.
            "GRINDGAINS_MCP_CREDENTIALS": str(tmp_path / "missing-credentials.json"),
        },
    )
    stderr_log = (tmp_path / "server-stderr.log").open("w")

    async def run():
        async with stdio_client(params, errlog=stderr_log) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await scenario(session)

    try:
        return asyncio.run(asyncio.wait_for(run(), timeout=60))
    finally:
        stderr_log.close()


def test_server_speaks_clean_mcp_over_stdio_and_lists_both_read_only_tools(tmp_path):
    async def scenario(session):
        return await session.list_tools()

    listed = run_against_real_server(tmp_path, scenario)

    tools = {tool.name: tool for tool in listed.tools}
    assert set(tools) == {"list_movements", "get_movement_history"}
    assert all(tool.annotations.read_only_hint for tool in tools.values())


def test_a_tool_call_without_a_saved_login_returns_a_clear_error(tmp_path):
    async def scenario(session):
        return await session.call_tool("list_movements", {})

    result = run_against_real_server(tmp_path, scenario)

    assert result.is_error is True
    text = " ".join(getattr(block, "text", "") for block in result.content)
    assert "No saved login found" in text
    assert "grindgains_mcp.login" in text


def test_stdout_carries_only_json_rpc_messages(tmp_path):
    """Drive the server with plain pipes (no SDK client, which tolerates stray lines)."""
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_movements", "arguments": {}}},
    ]
    proc = subprocess.Popen(
        [sys.executable, str(RUN_SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "GRINDGAINS_MCP_CREDENTIALS": str(tmp_path / "missing-credentials.json"),
            # print() to a pipe is block-buffered; unbuffered makes a stray print show up immediately.
            "PYTHONUNBUFFERED": "1",
        },
    )
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in proc.stdout], daemon=True).start()
    try:
        for request in requests:
            proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()

        messages = []
        while not any(m.get("id") == 2 for m in messages):
            line = lines.get(timeout=30)
            # A stray print() would make this line invalid JSON and fail the test here.
            message = json.loads(line)
            assert message.get("jsonrpc") == "2.0", f"not a JSON-RPC message: {line!r}"
            messages.append(message)
    finally:
        proc.stdin.close()
        proc.kill()
        proc.wait()

    by_id = {m["id"]: m for m in messages if "id" in m}
    assert by_id[1]["result"]["serverInfo"]["name"] == "grindgains"
    tool_result = by_id[2]["result"]
    assert tool_result["isError"] is True
    assert "No saved login found" in tool_result["content"][0]["text"]
