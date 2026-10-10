"""Entry point for MCP clients such as Claude Desktop.

Claude Desktop starts servers with an undefined working directory, so this script adds its own
directory to the import path instead of relying on `python -m` from the right folder.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from grindgains_mcp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
