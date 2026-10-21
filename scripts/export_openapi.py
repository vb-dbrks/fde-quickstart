"""Write the API's OpenAPI schema to a file; `make api-types` turns it into frontend TypeScript types.

Usage: uv run python scripts/export_openapi.py .build/openapi.json
"""

import json
import sys
from pathlib import Path

from backend.main import create_app
from backend.settings import Settings


def main() -> None:
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    # Building the schema does not touch the database or the agent; the defaults are enough.
    schema = create_app(Settings(_env_file=None)).openapi()
    target.write_text(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    main()
