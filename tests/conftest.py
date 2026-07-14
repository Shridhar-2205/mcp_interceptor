"""Make the project modules importable from the tests."""

import os
import sys

# tests/ -> project root (so `import mcp_client`, `import mcp_server`, etc. resolve)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
