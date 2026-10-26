"""Opt-in billable SDK smoke test; accepts only the checked-in fictional fixture."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

from .agents_sdk_adapter import MODEL_DEFAULT, run_live_fixture
from .coordinator import run

# The smoke test is deliberately NOT a general-purpose data ingestion endpoint.
# Update this digest in a reviewed PR only when the fictional fixture changes.
FIXTURE_SHA256 = "c73a02f9b2e5cebc89bf5caad9b212ec3b5d02aec12a531a3cc9b635f2c2a49c"
BUNDLED_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "purchase.json"


def read_bundled_fixture(path: Path) -> dict:
    if path.resolve() != BUNDLED_FIXTURE.resolve():
        raise ValueError("live smoke test accepts only the bundled fictional fixture")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != FIXTURE_SHA256:
        raise ValueError("bundled fictional fixture changed; review and update SHA256 first")
    request = json.loads(content)
    run(request)  # Check read-only restrictions before any optional model call.
    return request


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded, optional V2 specialist API smoke test")
    parser.add_argument("fixture", help="Checked-in fictional purchase fixture only")
    parser.add_argument("--check-only", action="store_true", help="Verify readiness; never call a model")
    parser.add_argument("--allow-api-calls", action="store_true", help="Explicitly authorize billable SDK calls")
    parser.add_argument("--model", default=MODEL_DEFAULT)
    args = parser.parse_args()

    try:
        request = read_bundled_fixture(Path(args.fixture))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    if args.check_only:
        print(json.dumps({
            "fixture_verified": True,
            "sdk_installed": importlib.util.find_spec("agents") is not None,
            "api_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
            "mode": "offline_check_only", "model_calls": 0,
            "max_specialist_calls": len(request["domains"]),
            "writes_permitted": False,
        }, indent=2))
        return

    if not args.allow_api_calls:
        parser.error("live calls are disabled unless --allow-api-calls is provided")
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is missing; no API calls were made")
    if importlib.util.find_spec("agents") is None:
        parser.error("OpenAI Agents SDK is missing; install requirements-live.txt first")

    result = run_live_fixture(request, model=args.model, allow_api_calls=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
