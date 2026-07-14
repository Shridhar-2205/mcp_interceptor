"""Make the mcp_lab package modules importable from the tests."""

import os
import sys

# tests/ -> mcp_lab/  (so `import mcp_client`, `import mcp_server`, etc. resolve)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
