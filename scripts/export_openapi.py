"""Export the FastAPI schema to openapi.yaml.

Usage: uv run python scripts/export_openapi.py
"""
import yaml
from backend.main import app

if __name__ == "__main__":
    schema = app.openapi()
    with open("openapi.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(schema, f, sort_keys=False, allow_unicode=True)
    print("openapi.yaml updated")
