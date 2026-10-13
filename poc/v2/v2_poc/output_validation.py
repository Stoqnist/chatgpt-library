"""Fail-closed policy gate for model-generated review signals in the V2 fixture.

Model prose is never evidence. Only narrow issue codes can produce a question
after independent checks against scoped fixture records. This module performs
no I/O, model calls or record mutations.
"""
from __future__ import annotations

import re
from typing import Any

ALLOWED_CODES = frozenset({"delivery_unconfirmed", "receipt_payment_link_unverified"})
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def _safe_id(value: Any) -> str | None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        return None
    return value


def review_signal(domain: str, code: str, evidence_ids: list[str],
                  scoped_evidence: list[dict]) -> str | None:
    """Return only a policy-authored question, or reject the AI suggestion.

    Evidence-ID existence alone is insufficient; every code has an explicit
    owner, source-type and factual precondition.
    """
    if code not in ALLOWED_CODES or len(set(evidence_ids)) != len(evidence_ids):
        return None
    by_id = {str(e["evidence_id"]): e for e in scoped_evidence}
    if not evidence_ids or any(key not in by_id for key in evidence_ids):
        return None
    refs = [by_id[key] for key in evidence_ids]

    if code == "delivery_unconfirmed":
        if domain not in {"purchase", "home"} or len(refs) != 1:
            return None
        receipt = refs[0]
        if receipt["source_type"] != "receipt":
            return None
        data = receipt["data"]
        item = _safe_id(data.get("item_id"))
        if data.get("status") != "completed" or not item:
            return None
        if data.get("delivered") is True or data.get("received") is True:
            return None
        return f"Was {item} actually received into the household?"

    if code == "receipt_payment_link_unverified":
        if domain != "finance" or len(refs) != 2:
            return None
        receipts = [e for e in refs if e["source_type"] == "receipt"]
        payments = [e for e in refs if e["source_type"] == "bank_transaction"]
        if len(receipts) != 1 or len(payments) != 1:
            return None
        receipt, payment = receipts[0]["data"], payments[0]["data"]
        rid, tid = _safe_id(receipt.get("receipt_id")), _safe_id(payment.get("transaction_id"))
        if not rid or not tid or receipt.get("status") != "completed":
            return None
        if payment.get("kind") != "card_purchase":
            return None
        # An explicitly shared identifier supports the link. Equal amounts do not.
        if receipt.get("transaction_id") == tid or payment.get("receipt_id") == rid:
            return None
        return f"Does card transaction {tid} belong to receipt {rid}?"

    return None
