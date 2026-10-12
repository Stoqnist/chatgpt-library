"""Explicitly opt-in to live, billable Agents SDK calls on synthetic fixtures."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .agents_sdk_adapter import MODEL_DEFAULT, run_live_fixture


def main() -> None:
    parser = argparse.ArgumentParser(description="Opt-in live V2 synthetic specialist smoke test")
    parser.add_argument("fixture", help="JSON file containing only fictional/synthetic evidence")
    parser.add_argument("--allow-api-calls", action="store_true", help="Allow paid model API requests")
    parser.add_argument("--model", default=MODEL_DEFAULT)
    args = parser.parse_args()

    if not args.allow_api_calls:
        parser.error("live calls are disabled unless --allow-api-calls is provided")
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is missing; no API calls were made")

    request = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    result = run_live_fixture(request, model=args.model, allow_api_calls=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
