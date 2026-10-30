"""Health check for CI, Docker and operators:  python health.py   (exit 0 = healthy)."""
import json
import sys

import config
from database.db import connect, schema_version, MIGRATIONS


def check(path: str | None = None) -> dict:
    errors, warnings = config.validate()
    checks = {"config": {"ok": not errors, "errors": errors, "warnings": warnings}}
    try:
        with connect(path) as con:
            v = schema_version(con)
        checks["database"] = {"ok": v == MIGRATIONS[-1][0], "schema_version": v}
    except Exception as e:
        checks["database"] = {"ok": False, "error": type(e).__name__}
    checks["ai_configured"] = {"ok": True, "enabled": config.llm_configured() and bool(config.LLM_MODEL)}  # informational
    return {"status": "ok" if all(c["ok"] for c in checks.values()) else "error", "checks": checks}


if __name__ == "__main__":
    result = check()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "ok" else 1)
