"""Export the FastAPI OpenAPI JSON to stdout.
Usage: python tools/export_openapi.py > openapi.json
"""
from main import app
import json

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2))
