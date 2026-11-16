import sys
from pathlib import Path

# Add backend directory to sys.path
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.main import app

# Vercel serverless function entrypoint
