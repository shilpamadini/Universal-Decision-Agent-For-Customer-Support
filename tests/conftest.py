import sys
from pathlib import Path

# Resolve the project root directory (folder that contains `agentic/`)
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
