from __future__ import annotations

import logging
import sys
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import training
from .api import GrindGainsClient
from .credentials import default_credentials_path, load
from .errors import GrindGainsError
from .training import Movement, TrainingEntry

logger = logging.getLogger("grindgains_mcp")

# Every tool only reads; none of them can change or delete data.
READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


class TrainingApi(Protocol):
    def list_movements(self) -> list[dict]: ...

    def get_movement_history(self, movement_id: str) -> list[dict]: ...


def create_server(get_client: Callable[[], TrainingApi], zone: ZoneInfo | None = None) -> MCPServer:
    tz = zone or training.get_timezone()
    server = MCPServer(
        "grindgains",
        instructions=(
            "Read-only access to the signed-in user's own GrindGains training log. "
            f"Dates and times are in the {tz.key} timezone. Weights are in pounds and hold times in seconds. "
            "The tools return recorded facts only."
        ),
    )

    @server.tool(annotations=READ_ONLY)
    def list_movements() -> list[Movement]:
        """List every movement (exercise) the user has logged, most recently trained first.

        Each item has the movement id, a display name, its mode (isotonic = sets x reps with a load,
        mobeta = timed isometric hold), how many entries are logged and the local date of the latest one.
        """
        try:
            client = get_client()
            movements = [
                training.to_movement(row["movement_id"], client.get_movement_history(row["movement_id"]), tz)
                for row in client.list_movements()
            ]
        except GrindGainsError as err:
            raise ToolError(str(err)) from None
        return sorted(movements, key=lambda m: (m.last_logged_date_local, m.movement_id), reverse=True)

    @server.tool(annotations=READ_ONLY)
    def get_movement_history(movement_id: str) -> list[TrainingEntry]:
        """Get every logged entry for one movement, oldest first.

        movement_id is the id from list_movements (letters, digits, underscore or hyphen, up to 128 characters).
        Each entry has the local timestamp and date, weight in pounds, reps (isotonic) or hold_seconds (mobeta),
        sets and RPE (null when not recorded).
        """
        try:
            validated = training.validate_movement_id(movement_id)
            return training.to_entries(get_client().get_movement_history(validated), tz)
        except GrindGainsError as err:
            raise ToolError(str(err)) from None

    return server


def main() -> None:
    # stdout carries the MCP protocol, so all logging goes to stderr.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
    holder: dict[str, GrindGainsClient] = {}

    def get_client() -> GrindGainsClient:
        if "client" not in holder:
            holder["client"] = GrindGainsClient(load(default_credentials_path()))
        return holder["client"]

    create_server(get_client).run()


if __name__ == "__main__":
    main()
