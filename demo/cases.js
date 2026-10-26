window.DEMO_CASES = [
  {
    "key": "overlap",
    "title": "The overlapping export",
    "detail": "Two bank rows. One payment. What actually counts?",
    "evidence": [
      {
        "evidence_id": "receipt-a",
        "source_type": "receipt",
        "source_locator": "fixture://purchase-receipt",
        "observed_at": "2026-10-01T10:00:00Z",
        "data": {
          "receipt_id": "R-123",
          "item_id": "desk-lamp",
          "amount_eur": "49.90",
          "status": "completed"
        }
      },
      {
        "evidence_id": "bank-a",
        "source_type": "bank_transaction",
        "source_locator": "fixture://bank-export",
        "observed_at": "2026-10-02T10:00:00Z",
        "data": {
          "source_account": "acct-a",
          "transaction_id": "T-001",
          "amount_eur": "49.90",
          "kind": "card_purchase"
        }
      },
      {
        "evidence_id": "bank-a-repeat",
        "source_type": "bank_transaction",
        "source_locator": "fixture://bank-overlap",
        "observed_at": "2026-10-03T10:00:00Z",
        "data": {
          "source_account": "acct-a",
          "transaction_id": "T-001",
          "amount_eur": "49.90",
          "kind": "card_purchase"
        }
      },
      {
        "evidence_id": "bank-own-transfer",
        "source_type": "bank_transaction",
        "source_locator": "fixture://bank-export",
        "observed_at": "2026-10-02T10:00:00Z",
        "data": {
          "source_account": "acct-a",
          "transaction_id": "T-002",
          "amount_eur": "100.00",
          "kind": "own_account_transfer"
        }
      }
    ],
    "result": {
      "run_id": "public-demo-overlap",
      "request_id": "public-demo-overlap",
      "simulation": true,
      "read_only": true,
      "status": "completed",
      "invoked_domains": [
        "purchase",
        "finance",
        "home"
      ],
      "specialist_results": {
        "purchase": {
          "domain_owner": "purchase",
          "status": "completed",
          "findings": [
            {
              "claim": "Purchase completed for desk-lamp; receipt amount EUR 49.90.",
              "evidence_ids": [
                "receipt-a"
              ],
              "provenance": "source-verified",
              "limitation": ""
            }
          ],
          "proposed_writes": [
            {
              "domain_owner": "purchase",
              "canonical_destination": "/Purchases/purchase-lifecycle.md",
              "change": "Record verified acquisition of desk-lamp",
              "evidence_ids": [
                "receipt-a"
              ],
              "approval_required": true,
              "executed": false,
              "verified": false
            }
          ],
          "unresolved_questions": [],
          "error": null
        },
        "finance": {
          "domain_owner": "finance",
          "status": "completed",
          "findings": [
            {
              "claim": "Identified 1 unique card purchase(s), totaling EUR 49.90.",
              "evidence_ids": [
                "bank-a"
              ],
              "provenance": "source-verified",
              "limitation": ""
            },
            {
              "claim": "Own-account transfers excluded from spending.",
              "evidence_ids": [
                "bank-own-transfer"
              ],
              "provenance": "source-verified",
              "limitation": ""
            },
            {
              "claim": "Repeated bank transaction identifiers excluded from totals.",
              "evidence_ids": [
                "bank-a-repeat"
              ],
              "provenance": "source-verified",
              "limitation": ""
            }
          ],
          "proposed_writes": [
            {
              "domain_owner": "finance",
              "canonical_destination": "/Finance/personal-finance-record.md",
              "change": "Review categorized spending of EUR 49.90",
              "evidence_ids": [
                "bank-a"
              ],
              "approval_required": true,
              "executed": false,
              "verified": false
            }
          ],
          "unresolved_questions": [],
          "error": null
        },
        "home": {
          "domain_owner": "home",
          "status": "completed",
          "findings": [
            {
              "claim": "Completed acquisition of desk-lamp supports a proposed ownership check; physical receipt/location still unverified.",
              "evidence_ids": [
                "receipt-a"
              ],
              "provenance": "source-verified",
              "limitation": "No observation proving delivery or household possession."
            }
          ],
          "proposed_writes": [],
          "unresolved_questions": [
            "Was desk-lamp actually received into the household?"
          ],
          "error": null
        }
      },
      "findings": [
        {
          "domain_owner": "purchase",
          "claim": "Purchase completed for desk-lamp; receipt amount EUR 49.90.",
          "evidence_ids": [
            "receipt-a"
          ],
          "provenance": "source-verified",
          "limitation": ""
        },
        {
          "domain_owner": "finance",
          "claim": "Identified 1 unique card purchase(s), totaling EUR 49.90.",
          "evidence_ids": [
            "bank-a"
          ],
          "provenance": "source-verified",
          "limitation": ""
        },
        {
          "domain_owner": "finance",
          "claim": "Own-account transfers excluded from spending.",
          "evidence_ids": [
            "bank-own-transfer"
          ],
          "provenance": "source-verified",
          "limitation": ""
        },
        {
          "domain_owner": "finance",
          "claim": "Repeated bank transaction identifiers excluded from totals.",
          "evidence_ids": [
            "bank-a-repeat"
          ],
          "provenance": "source-verified",
          "limitation": ""
        },
        {
          "domain_owner": "home",
          "claim": "Completed acquisition of desk-lamp supports a proposed ownership check; physical receipt/location still unverified.",
          "evidence_ids": [
            "receipt-a"
          ],
          "provenance": "source-verified",
          "limitation": "No observation proving delivery or household possession."
        }
      ],
      "unresolved_questions": [
        "Was desk-lamp actually received into the household?"
      ],
      "proposed_writes": [
        {
          "domain_owner": "purchase",
          "canonical_destination": "/Purchases/purchase-lifecycle.md",
          "change": "Record verified acquisition of desk-lamp",
          "evidence_ids": [
            "receipt-a"
          ],
          "approval_required": true,
          "executed": false,
          "verified": false
        },
        {
          "domain_owner": "finance",
          "canonical_destination": "/Finance/personal-finance-record.md",
          "change": "Review categorized spending of EUR 49.90",
          "evidence_ids": [
            "bank-a"
          ],
          "approval_required": true,
          "executed": false,
          "verified": false
        }
      ],
      "executed_writes": [],
      "failures_or_blocks": [],
      "notice": "Synthetic simulation only: no model calls, live sources, or record updates."
    }
  },
  {
    "key": "conflict",
    "title": "The conflicting amount",
    "detail": "The same payment appears as €49.90 and €59.90. Can we trust the total?",
    "evidence": [
      {
        "evidence_id": "receipt-a",
        "source_type": "receipt",
        "source_locator": "fixture://purchase-receipt",
        "observed_at": "2026-10-01T10:00:00Z",
        "data": {
          "receipt_id": "R-123",
          "item_id": "desk-lamp",
          "amount_eur": "49.90",
          "status": "completed"
        }
      },
      {
        "evidence_id": "bank-a",
        "source_type": "bank_transaction",
        "source_locator": "fixture://bank-export",
        "observed_at": "2026-10-02T10:00:00Z",
        "data": {
          "source_account": "acct-a",
          "transaction_id": "T-001",
          "amount_eur": "49.90",
          "kind": "card_purchase"
        }
      },
      {
        "evidence_id": "bank-a-repeat",
        "source_type": "bank_transaction",
        "source_locator": "fixture://bank-overlap",
        "observed_at": "2026-10-03T10:00:00Z",
        "data": {
          "source_account": "acct-a",
          "transaction_id": "T-001",
          "amount_eur": "59.90",
          "kind": "card_purchase"
        }
      },
      {
        "evidence_id": "bank-own-transfer",
        "source_type": "bank_transaction",
        "source_locator": "fixture://bank-export",
        "observed_at": "2026-10-02T10:00:00Z",
        "data": {
          "source_account": "acct-a",
          "transaction_id": "T-002",
          "amount_eur": "100.00",
          "kind": "own_account_transfer"
        }
      }
    ],
    "result": {
      "run_id": "public-demo-conflict",
      "request_id": "public-demo-conflict",
      "simulation": true,
      "read_only": true,
      "status": "partial",
      "invoked_domains": [
        "purchase",
        "finance",
        "home"
      ],
      "specialist_results": {
        "purchase": {
          "domain_owner": "purchase",
          "status": "completed",
          "findings": [
            {
              "claim": "Purchase completed for desk-lamp; receipt amount EUR 49.90.",
              "evidence_ids": [
                "receipt-a"
              ],
              "provenance": "source-verified",
              "limitation": ""
            }
          ],
          "proposed_writes": [
            {
              "domain_owner": "purchase",
              "canonical_destination": "/Purchases/purchase-lifecycle.md",
              "change": "Record verified acquisition of desk-lamp",
              "evidence_ids": [
                "receipt-a"
              ],
              "approval_required": true,
              "executed": false,
              "verified": false
            }
          ],
          "unresolved_questions": [],
          "error": null
        },
        "finance": {
          "domain_owner": "finance",
          "status": "blocked",
          "findings": [],
          "proposed_writes": [],
          "unresolved_questions": [
            "Conflicting data for transaction T-001 in acct-a; verify original statements."
          ],
          "error": null
        },
        "home": {
          "domain_owner": "home",
          "status": "completed",
          "findings": [
            {
              "claim": "Completed acquisition of desk-lamp supports a proposed ownership check; physical receipt/location still unverified.",
              "evidence_ids": [
                "receipt-a"
              ],
              "provenance": "source-verified",
              "limitation": "No observation proving delivery or household possession."
            }
          ],
          "proposed_writes": [],
          "unresolved_questions": [
            "Was desk-lamp actually received into the household?"
          ],
          "error": null
        }
      },
      "findings": [
        {
          "domain_owner": "purchase",
          "claim": "Purchase completed for desk-lamp; receipt amount EUR 49.90.",
          "evidence_ids": [
            "receipt-a"
          ],
          "provenance": "source-verified",
          "limitation": ""
        },
        {
          "domain_owner": "home",
          "claim": "Completed acquisition of desk-lamp supports a proposed ownership check; physical receipt/location still unverified.",
          "evidence_ids": [
            "receipt-a"
          ],
          "provenance": "source-verified",
          "limitation": "No observation proving delivery or household possession."
        }
      ],
      "unresolved_questions": [
        "Conflicting data for transaction T-001 in acct-a; verify original statements.",
        "Was desk-lamp actually received into the household?"
      ],
      "proposed_writes": [
        {
          "domain_owner": "purchase",
          "canonical_destination": "/Purchases/purchase-lifecycle.md",
          "change": "Record verified acquisition of desk-lamp",
          "evidence_ids": [
            "receipt-a"
          ],
          "approval_required": true,
          "executed": false,
          "verified": false
        }
      ],
      "executed_writes": [],
      "failures_or_blocks": [
        "finance"
      ],
      "notice": "Synthetic simulation only: no model calls, live sources, or record updates."
    }
  },
  {
    "key": "missing",
    "title": "The missing receipt",
    "detail": "A bank payment exists. Is that enough to add something to your home?",
    "evidence": [
      {
        "evidence_id": "bank-a",
        "source_type": "bank_transaction",
        "source_locator": "fixture://bank-export",
        "observed_at": "2026-10-02T10:00:00Z",
        "data": {
          "source_account": "acct-a",
          "transaction_id": "T-001",
          "amount_eur": "49.90",
          "kind": "card_purchase"
        }
      },
      {
        "evidence_id": "bank-a-repeat",
        "source_type": "bank_transaction",
        "source_locator": "fixture://bank-overlap",
        "observed_at": "2026-10-03T10:00:00Z",
        "data": {
          "source_account": "acct-a",
          "transaction_id": "T-001",
          "amount_eur": "49.90",
          "kind": "card_purchase"
        }
      },
      {
        "evidence_id": "bank-own-transfer",
        "source_type": "bank_transaction",
        "source_locator": "fixture://bank-export",
        "observed_at": "2026-10-02T10:00:00Z",
        "data": {
          "source_account": "acct-a",
          "transaction_id": "T-002",
          "amount_eur": "100.00",
          "kind": "own_account_transfer"
        }
      }
    ],
    "result": {
      "run_id": "public-demo-missing",
      "request_id": "public-demo-missing",
      "simulation": true,
      "read_only": true,
      "status": "partial",
      "invoked_domains": [
        "purchase",
        "finance",
        "home"
      ],
      "specialist_results": {
        "purchase": {
          "domain_owner": "purchase",
          "status": "blocked",
          "findings": [],
          "proposed_writes": [],
          "unresolved_questions": [
            "Provide purchase receipt or order evidence."
          ],
          "error": null
        },
        "finance": {
          "domain_owner": "finance",
          "status": "completed",
          "findings": [
            {
              "claim": "Identified 1 unique card purchase(s), totaling EUR 49.90.",
              "evidence_ids": [
                "bank-a"
              ],
              "provenance": "source-verified",
              "limitation": ""
            },
            {
              "claim": "Own-account transfers excluded from spending.",
              "evidence_ids": [
                "bank-own-transfer"
              ],
              "provenance": "source-verified",
              "limitation": ""
            },
            {
              "claim": "Repeated bank transaction identifiers excluded from totals.",
              "evidence_ids": [
                "bank-a-repeat"
              ],
              "provenance": "source-verified",
              "limitation": ""
            }
          ],
          "proposed_writes": [
            {
              "domain_owner": "finance",
              "canonical_destination": "/Finance/personal-finance-record.md",
              "change": "Review categorized spending of EUR 49.90",
              "evidence_ids": [
                "bank-a"
              ],
              "approval_required": true,
              "executed": false,
              "verified": false
            }
          ],
          "unresolved_questions": [],
          "error": null
        },
        "home": {
          "domain_owner": "home",
          "status": "blocked",
          "findings": [],
          "proposed_writes": [],
          "unresolved_questions": [
            "Require confirmed purchase analysis before proposing a household inventory update."
          ],
          "error": null
        }
      },
      "findings": [
        {
          "domain_owner": "finance",
          "claim": "Identified 1 unique card purchase(s), totaling EUR 49.90.",
          "evidence_ids": [
            "bank-a"
          ],
          "provenance": "source-verified",
          "limitation": ""
        },
        {
          "domain_owner": "finance",
          "claim": "Own-account transfers excluded from spending.",
          "evidence_ids": [
            "bank-own-transfer"
          ],
          "provenance": "source-verified",
          "limitation": ""
        },
        {
          "domain_owner": "finance",
          "claim": "Repeated bank transaction identifiers excluded from totals.",
          "evidence_ids": [
            "bank-a-repeat"
          ],
          "provenance": "source-verified",
          "limitation": ""
        }
      ],
      "unresolved_questions": [
        "Provide purchase receipt or order evidence.",
        "Require confirmed purchase analysis before proposing a household inventory update."
      ],
      "proposed_writes": [
        {
          "domain_owner": "finance",
          "canonical_destination": "/Finance/personal-finance-record.md",
          "change": "Review categorized spending of EUR 49.90",
          "evidence_ids": [
            "bank-a"
          ],
          "approval_required": true,
          "executed": false,
          "verified": false
        }
      ],
      "executed_writes": [],
      "failures_or_blocks": [
        "purchase",
        "home"
      ],
      "notice": "Synthetic simulation only: no model calls, live sources, or record updates."
    }
  }
];
