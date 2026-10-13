"""Minimal shared mechanics for fictional read-only journey runners.

No triage, routing, semantic evaluation, permissions or provider execution.
"""
def supersede_unexecuted(proposals):
    """Block prior unexecuted proposals on a new turn; return withdrawn IDs.

    Already blocked or terminal actions are left unchanged. This intentionally
    implements S4's conservative blanket invalidation, not selective dependencies.
    """
    withdrawn = []
    for proposal in proposals:
        if proposal["status"] == "proposed":
            proposal["status"] = "blocked"
            proposal["reason"] = "superseded"
            withdrawn.append(proposal["operation_id"])
    return withdrawn
