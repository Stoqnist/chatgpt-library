#!/usr/bin/env python3
"""Validate the public templates without connecting to any personal account."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH = ROOT / "library/Architecture/family-agent-architecture.md"
STATE = ROOT / "library/Architecture/file-backed-state-policy.md"
EXPECTED = {
    ARCH: {"INVENTORY_SPREADSHEET_ID", "INVENTORY_STOCK_SHEET_ID", "FOOD_PREFERENCES_RECORD_PATH", "MENTAL_WELLBEING_RECORD_PATH", "RECORD_OWNER_NAME", "SOURCE_COMMIT"},
    STATE: {"SOURCE_COMMIT"},
}
for path, keys in EXPECTED.items():
    text = path.read_bytes().decode("utf-8")
    actual = set(re.findall(r"\{\{([A-Z_]+)\}\}", text))
    assert actual == keys, (path.name, actual, keys)
    assert text.endswith("\n"), path.name
    assert not re.search(r"(?:libfile_|file_000000|/Health/[a-z]+-(?:food-preferences|mental-wellbeing-record))", text), path.name
    assert not re.search(r"spreadsheets/d/(?!\{\{)[A-Za-z0-9_-]+", text), path.name
    assert "Published source commit: `{{SOURCE_COMMIT}}`." in text, path.name
arch = ARCH.read_text()
state = STATE.read_text()
for rule in ("Exactly one current row per Item ID", "Unknown quantity is blank, never zero", "Sheets does not provide database-level compare-and-set", "Home & Possessions remains the inventory owner"):
    assert rule in arch, rule
assert "redirect only" in state
assert "Git-managed instructions" in arch
assert "private operational state" in arch
# Static checks for the two specialist prompts and their single ownership source.
PROMPTS = {
    "Venture & Capital Architect": ROOT / "library/Agents/venture-capital-architect-system-prompt.md",
    "Netherlands Legal & Regulatory Research Specialist": ROOT / "library/Agents/netherlands-legal-regulatory-research-specialist-system-prompt.md",
}
for name, path in PROMPTS.items():
    prompt = path.read_text(encoding="utf-8")
    assert prompt.startswith(f"# {name}\\n"), path
    assert prompt.endswith("\\n"), path
    for heading in ("[IDENTITY & ROLE]", "[CAPABILITIES & SCOPE]", "[EXECUTION AUTHORITY]", "[CONSTRAINTS & GUARDRAILS]"):
        assert f"## {heading}" in prompt, (path, heading)
    assert len(prompt) <= 8000, path
    assert arch.count(f"**{name}** —") == 1, name
    assert not re.search(r"libfile_|file_000000|spreadsheets/d/[A-Za-z0-9_-]+", prompt), path
business = ROOT / "business/stoqnist/README.md"
brief = business.read_text(encoding="utf-8")
for path in PROMPTS.values():
    assert f"../../{path.relative_to(ROOT).as_posix()}" in brief, path
assert "concept and research brief" in brief
print("PASS: template bindings, publication metadata, inventory rules and specialist boundaries")
