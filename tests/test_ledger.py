# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eduseed_pipeline.ledger import build_ledger, index_by_challenge, render  # noqa: E402


SUB_A1 = {"challenge_id": "ch-a", "submission_id": "sub-1", "task_state": "needs_revision",
          "submitted_at": "2026-11-03T07:45:05"}
SUB_A2 = {"challenge_id": "ch-a", "submission_id": "sub-2", "task_state": "pending_teacher_review",
          "submitted_at": "2026-11-03T12:38:32"}
SUB_B = {"challenge_id": "ch-b", "submission_id": "sub-3", "task_state": "pending_teacher_review",
         "submitted_at": "2026-11-03T13:49:46"}


class TestIndex(unittest.TestCase):
    def test_groups_and_sorts_ascending(self):
        groups = index_by_challenge([SUB_A2, SUB_A1])
        self.assertEqual([s["submission_id"] for s in groups["ch-a"]], ["sub-1", "sub-2"])

    def test_skips_missing_challenge_id(self):
        groups = index_by_challenge([{"submission_id": "no-cid"}])
        self.assertEqual(groups, {})


class TestLedger(unittest.TestCase):
    def test_counts_records_and_covered_separately(self):
        # 真实场景：C5 被打回后重提，列表里两条记录，但只覆盖一个挑战
        led = build_ledger([SUB_A1, SUB_A2, SUB_B])
        self.assertEqual(led["records"], 3)
        self.assertEqual(led["covered"], 2)

    def test_latest_state_wins(self):
        led = build_ledger([SUB_A1, SUB_A2])
        item = led["items"][0]
        self.assertEqual(item["submission_id"], "sub-2")
        self.assertEqual(item["state"], "pending_teacher_review")

    def test_duplicates_surfaced_explicitly(self):
        led = build_ledger([SUB_A1, SUB_A2, SUB_B])
        self.assertEqual(len(led["duplicated_challenges"]), 1)
        self.assertEqual(led["duplicated_challenges"][0]["challenge_id"], "ch-a")
        self.assertEqual(led["duplicated_challenges"][0]["records"], 2)

    def test_no_duplicates_key_when_each_unique(self):
        led = build_ledger([SUB_B])
        self.assertEqual(led["duplicated_challenges"], [])

    def test_state_distribution_counts_challenges_not_records(self):
        led = build_ledger([SUB_A1, SUB_A2, SUB_B])
        self.assertEqual(led["latest_state_counts"], {"pending_teacher_review": 2})

    def test_not_submitted_computed_from_challenges(self):
        challenges = [
            {"challenge_id": "ch-a", "title": "C1"},
            {"challenge_id": "ch-b", "title": "C2"},
            {"challenge_id": "ch-c", "title": "C3"},
        ]
        led = build_ledger([SUB_A1, SUB_B], challenges)
        self.assertEqual([x["challenge_id"] for x in led["not_submitted"]], ["ch-c"])

    def test_titles_pulled_from_challenge_list(self):
        led = build_ledger([SUB_B], [{"challenge_id": "ch-b", "title": "C6 Web"}])
        self.assertEqual(led["items"][0]["title"], "C6 Web")

    def test_unknown_time_does_not_crash(self):
        led = build_ledger([{"challenge_id": "ch-z", "submission_id": "s", "submitted_at": None}])
        self.assertEqual(led["covered"], 1)

    def test_render_mentions_duplicate(self):
        text = render(build_ledger([SUB_A1, SUB_A2]))
        self.assertIn("ch-a×2", text)

    def test_render_lists_pending_challenges(self):
        text = render(build_ledger([], [{"challenge_id": "ch-q", "title": "C10"}]))
        self.assertIn("C10", text)


if __name__ == "__main__":
    unittest.main()
