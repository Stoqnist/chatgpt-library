"""Read-only deterministic V2 orchestration POC.

No provider SDK, network operations, filesystem writes, or external actions occur
inside this module. Specialist handlers simulate bounded domain decisions from
synthetic evidence, and are replaceable with real adapters after approval.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

DOMAINS = ("purchase", "finance", "home")
DESTINATIONS = {
    "purchase": "/Purchases/purchase-lifecycle.md",
    "finance": "/Finance/personal-finance-record.md",
    "home": "/Home & Possessions/home-possessions-record.md",
}
STATUSES = {"completed", "partial", "blocked", "failed"}


def _amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError("invalid monetary amount") from None


def _finding(claim: str, evidence: list[str], provenance: str = "source-verified", *, limitation: str = "") -> dict[str, Any]:
    return {"claim": claim, "evidence_ids": evidence, "provenance": provenance, "limitation": limitation}


def _proposed_write(owner: str, text: str, evidence: list[str]) -> dict[str, Any]:
    return {"domain_owner": owner, "canonical_destination": DESTINATIONS[owner],
            "change": text, "evidence_ids": evidence, "approval_required": True,
            "executed": False, "verified": False}


def _result(owner: str, *, status: str = "completed", findings: list | None = None,
            proposed_writes: list | None = None, questions: list | None = None,
            error: str | None = None) -> dict[str, Any]:
    return {"domain_owner": owner, "status": status, "findings": findings or [],
            "proposed_writes": proposed_writes or [], "unresolved_questions": questions or [],
            "error": error}


def _evidence_for(items: list[dict], source_type: str) -> list[dict]:
    return [item for item in items if item["source_type"] == source_type]


def purchase_specialist(items: list[dict], results: dict[str, dict]) -> dict:
    receipts = _evidence_for(items, "receipt")
    if not receipts:
        return _result("purchase", status="blocked", questions=["Provide purchase receipt or order evidence."])
    completed = [e for e in receipts if e["data"].get("status") == "completed"]
    if not completed:
        return _result("purchase", status="partial", findings=[_finding(
            "A receipt or order record exists, but a completed purchase is not established.",
            [e["evidence_id"] for e in receipts])],
            questions=["Was the purchase completed?"])
    r = completed[0]
    item = r["data"].get("item_id", "unspecified item")
    return _result("purchase", findings=[_finding(
        f"Purchase completed for {item}; receipt amount EUR {r['data']['amount_eur']}.",
        [r["evidence_id"]])],
        proposed_writes=[_proposed_write("purchase", f"Record verified acquisition of {item}", [r["evidence_id"]])])


def finance_specialist(items: list[dict], results: dict[str, dict]) -> dict:
    transactions = _evidence_for(items, "bank_transaction")
    if not transactions:
        return _result("finance", status="blocked", questions=["Provide bank transaction evidence."])
    seen: dict[tuple[str, str], dict] = {}
    purchases: list[dict] = []
    ignored_internal: list[str] = []
    duplicate_refs: list[str] = []
    for e in transactions:
        data = e["data"]
        key = (str(data.get("source_account", "unspecified")), str(data.get("transaction_id", "")))
        if not key[1]:
            return _result("finance", status="blocked", questions=["Missing bank transaction identifier; cannot deduplicate safely."])
        if key in seen:
            old = seen[key]["data"]
            # Overlapping exports may repeat a transaction, but conflicting
            # amount or classification is not safe to silently deduplicate.
            if any(old.get(field) != data.get(field) for field in ("kind", "amount_eur")):
                return _result("finance", status="blocked", questions=[
                    f"Conflicting data for transaction {key[1]} in {key[0]}; verify original statements."
                ])
            duplicate_refs.append(e["evidence_id"])
            continue
        seen[key] = e
        if data.get("kind") == "own_account_transfer":
            ignored_internal.append(e["evidence_id"])
        elif data.get("kind") == "card_purchase":
            purchases.append(e)
    total = sum((_amount(e["data"]["amount_eur"]) for e in purchases), Decimal("0"))
    refs = [e["evidence_id"] for e in purchases]
    findings = [_finding(f"Identified {len(purchases)} unique card purchase(s), totaling EUR {total:.2f}.", refs)]
    if ignored_internal:
        findings.append(_finding("Own-account transfers excluded from spending.", ignored_internal))
    if duplicate_refs:
        findings.append(_finding("Repeated bank transaction identifiers excluded from totals.", duplicate_refs))
    receipts = _evidence_for(items, "receipt")
    issues: list[str] = []
    if receipts and purchases:
        receipt_total = _amount(receipts[0]["data"]["amount_eur"])
        if receipt_total != total:
            issues.append(f"Receipt EUR {receipt_total:.2f} differs from unique bank card spending EUR {total:.2f}; allocation unresolved.")
    status = "partial" if issues else "completed"
    return _result("finance", status=status, findings=findings,
                   proposed_writes=[] if issues else [_proposed_write(
                       "finance", f"Review categorized spending of EUR {total:.2f}", refs)],
                   questions=issues)


def home_specialist(items: list[dict], results: dict[str, dict]) -> dict:
    purchase = results.get("purchase")
    if not purchase or purchase["status"] != "completed":
        return _result("home", status="blocked",
                       questions=["Require confirmed purchase analysis before proposing a household inventory update."])
    completed = [e for e in _evidence_for(items, "receipt") if e["data"].get("status") == "completed"]
    if not completed:
        return _result("home", status="blocked", questions=["No verified completed acquisition."])
    e = completed[0]
    item = str(e["data"].get("item_id", "unspecified item"))
    return _result("home", findings=[_finding(
        f"Completed acquisition of {item} supports a proposed ownership check; physical receipt/location still unverified.",
        [e["evidence_id"]], limitation="No observation proving delivery or household possession.")],
        proposed_writes=[], questions=[f"Was {item} actually received into the household?"])


SPECIALISTS: dict[str, Callable[[list[dict], dict[str, dict]], dict]] = {
    "purchase": purchase_specialist,
    "finance": finance_specialist,
    "home": home_specialist,
}


def _normalize_evidence(records: list[dict]) -> list[dict]:
    unique: dict[str, dict] = {}
    for e in records:
        if not isinstance(e, dict) or not all(k in e for k in ("evidence_id", "source_type", "source_locator", "observed_at", "data")):
            raise ValueError("evidence missing required provenance fields")
        if not str(e["source_locator"]).startswith("fixture://"):
            raise ValueError("POC only accepts synthetic fixture locators")
        if e["source_type"] not in {"receipt", "bank_transaction"} or not isinstance(e["data"], dict):
            raise ValueError("unsupported evidence source/data")
        key = str(e["evidence_id"])
        if key in unique and unique[key] != e:
            raise ValueError("conflicting entries share an evidence_id")
        unique[key] = e
    return list(unique.values())


def run(request: dict, handlers: dict[str, Callable] | None = None) -> dict:
    """Run a bounded, read-only simulation; return one consolidated structured result."""
    if not isinstance(request, dict) or not all(request.get(k) for k in ("run_id", "request_id", "user_goal")):
        raise ValueError("run_id, request_id and user_goal are required")
    requested = request.get("domains", [])
    if not isinstance(requested, list) or not requested or len(requested) > 3 or len(set(requested)) != len(requested):
        raise ValueError("one to three distinct domains required")
    if any(d not in DOMAINS for d in requested):
        raise ValueError("unsupported domain")
    if request.get("requested_actions") not in (None, [], ["read_only"]):
        raise ValueError("POC is read-only and cannot execute external actions")
    evidence = _normalize_evidence(request.get("evidence", []))
    adapters = handlers if handlers is not None else SPECIALISTS
    results: dict[str, dict] = {}
    # Minimum necessary evidence per specialist, not global bank-data broadcast.
    source_access = {
        "purchase": {"receipt"},
        "finance": {"receipt", "bank_transaction"},
        "home": {"receipt"},
    }
    # Dependencies are strict: Home runs only after Purchase. No recursive delegation.
    for domain in DOMAINS:
        if domain not in requested:
            continue
        scoped = [e for e in evidence if e["source_type"] in source_access[domain]]
        allowed_ids = {e["evidence_id"] for e in scoped}
        # Only Home may see prior purchase analysis. Other domain outputs are
        # not unnecessarily shared with unrelated specialist handlers.
        prior = {"purchase": results["purchase"]} if domain == "home" and "purchase" in results else {}
        try:
            if domain not in adapters:
                raise RuntimeError("specialist adapter unavailable")
            response = adapters[domain](scoped, prior)
            if response.get("domain_owner") != domain or response.get("status") not in STATUSES:
                raise ValueError("invalid specialist result contract")
            for finding in response.get("findings", []):
                if not set(finding.get("evidence_ids", [])).issubset(allowed_ids):
                    raise ValueError("specialist cited evidence outside its assigned scope")
                if finding.get("provenance") not in {"source-verified", "user-reported", "inferred", "unresolved"}:
                    raise ValueError("specialist returned invalid provenance")
            for write in response.get("proposed_writes", []):
                if not set(write.get("evidence_ids", [])).issubset(allowed_ids):
                    raise ValueError("write proposal cited evidence outside its assigned scope")
                if write.get("domain_owner") != domain or write.get("canonical_destination") != DESTINATIONS[domain]:
                    raise ValueError("specialist attempted out-of-domain write proposal")
                if write.get("executed") is not False or write.get("verified") is not False:
                    raise ValueError("specialist claimed execution in read-only POC")
            results[domain] = response
        except Exception as exc:
            results[domain] = _result(domain, status="failed", error=f"{type(exc).__name__}: {exc}")
    all_findings: list[dict] = []
    seen_claims: set[tuple] = set()
    for domain, response in results.items():
        for entry in response["findings"]:
            key = (entry["claim"], tuple(sorted(entry["evidence_ids"])))
            if key not in seen_claims:
                seen_claims.add(key)
                all_findings.append({"domain_owner": domain, **entry})
    questions = list(dict.fromkeys(q for x in results.values() for q in x["unresolved_questions"]))
    failures = [d for d, x in results.items() if x["status"] != "completed"]
    return {"run_id": request["run_id"], "request_id": request["request_id"],
            "simulation": True, "read_only": True, "status": "partial" if failures else "completed",
            "invoked_domains": list(results), "specialist_results": results,
            "findings": all_findings, "unresolved_questions": questions,
            "proposed_writes": [w for x in results.values() for w in x["proposed_writes"]],
            "executed_writes": [], "failures_or_blocks": failures,
            "notice": "Synthetic simulation only: no model calls, live sources, or record updates."}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Read-only V2 orchestration POC")
    parser.add_argument("fixture", help="Path to synthetic request JSON")
    args = parser.parse_args()
    with open(args.fixture, "r", encoding="utf-8") as handle:
        request = json.load(handle)
    print(json.dumps(run(request), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
