"""S2 focused mechanical regression; separate journey oracles stay independent."""
import copy
import unittest

from v2_poc.journey_mechanics import supersede_unexecuted


class SupersessionMechanicsTests(unittest.TestCase):
    def test_conservative_invalidation_and_terminal_preservation(self):
        proposals = [
            {"operation_id": "active-1", "status": "proposed"},
            {"operation_id": "old", "status": "blocked", "reason": "approval_denied"},
            {"operation_id": "active-2", "status": "proposed"},
            {"operation_id": "done", "status": "verified"},
        ]
        self.assertEqual(supersede_unexecuted(proposals), ["active-1", "active-2"])
        self.assertEqual([p["status"] for p in proposals],
                         ["blocked", "blocked", "blocked", "verified"])
        self.assertEqual(proposals[1]["reason"], "approval_denied")
        self.assertEqual(proposals[0]["reason"], "superseded")
        self.assertEqual(proposals[2]["reason"], "superseded")
        frozen = copy.deepcopy(proposals)
        self.assertEqual(supersede_unexecuted(proposals), [])
        self.assertEqual(proposals, frozen)

    def test_empty_previous_turn_has_no_effect(self):
        self.assertEqual(supersede_unexecuted([]), [])


if __name__ == "__main__":
    unittest.main()
