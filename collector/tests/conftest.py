import sys
from pathlib import Path

COLLECTOR_DIR = Path(__file__).parent.parent
if str(COLLECTOR_DIR) not in sys.path:
    sys.path.insert(0, str(COLLECTOR_DIR))
