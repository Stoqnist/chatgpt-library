"""Prove selected safety tests fail under isolated, controlled source regressions.

Run from poc/v2. No repository files are modified. No SDK/model calls occur.
A baseline failure, stale mutation anchor, test error, or surviving mutant fails.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SUITE = ["test_adversarial", "test_coordinator", "test_agents_sdk_adapter"]
MUTATIONS = (
    ("missing transaction identity", "coordinator.py", 'if not key[1]:', 'if False:'),
    ("conflicting transaction values", "coordinator.py",
     'if any(old.get(field) != data.get(field) for field in ("kind", "amount_eur")):', 'if False:'),
    ("cross-account transaction identity", "coordinator.py",
     'str(data.get("source_account", "unspecified"))', '"all-accounts"'),
    ("external action authority", "coordinator.py",
     'if request.get("requested_actions") not in (None, [], ["read_only"]):', 'if False:'),
    ("domain write ownership", "coordinator.py",
     'if write.get("domain_owner") != domain or write.get("canonical_destination") != DESTINATIONS[domain]:', 'if False:'),
    ("fabricated execution", "coordinator.py",
     'if write.get("executed") is not False or write.get("verified") is not False:', 'if False:'),
    ("evidence scope disclosure", "coordinator.py",
     'scoped = [e for e in evidence if e["source_type"] in source_access[domain]]', 'scoped = list(evidence)'),
    ("unsupported model prose", "agents_sdk_adapter.py",
     'rejected = len(assessment.findings) + len(assessment.questions)',
     'baseline["findings"].extend({"claim": f.claim, "evidence_ids": f.evidence_ids, "provenance": "source-verified"} for f in assessment.findings)\n            rejected = len(assessment.findings) + len(assessment.questions)'),
    ("invented model evidence", "output_validation.py",
     'if not evidence_ids or any(key not in by_id for key in evidence_ids):\n        return None',
     'if not evidence_ids or any(key not in by_id for key in evidence_ids):\n        return "UNTRUSTED invented evidence accepted?"'),
)


def check(root):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(root), str(root / "tests"))))
    return subprocess.run([sys.executable, "-B", "-m", "unittest", *SUITE],
                          cwd=root, env=env, text=True, capture_output=True, timeout=30)


def main():
    baseline = check(ROOT)
    if baseline.returncode:
        print("Baseline failed; mutation results would be invalid.\n" + baseline.stderr)
        return 1
    failures = []
    for name, filename, old, new in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="v2-mutation-") as temp:
            root = Path(temp)
            for directory in ("v2_poc", "tests", "fixtures"):
                shutil.copytree(ROOT / directory, root / directory,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            target = root / "v2_poc" / filename
            source = target.read_text()
            if source.count(old) != 1:
                failures.append(name)
                print(f"INVALID: {name}: expected exactly one source anchor")
                continue
            mutated = source.replace(old, new, 1)
            compile(mutated, str(target), "exec")
            target.write_text(mutated)
            result = check(root)
            # Import errors/crashes do not count as a killed safety regression.
            killed = result.returncode == 1 and "FAIL:" in result.stderr and "ERROR:" not in result.stderr
            print(f"{'KILLED' if killed else 'INVALID/SURVIVED'}: {name}")
            if not killed:
                failures.append(name)
                print(result.stderr)
    print(f"{len(MUTATIONS) - len(failures)}/{len(MUTATIONS)} controlled regressions detected")
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
