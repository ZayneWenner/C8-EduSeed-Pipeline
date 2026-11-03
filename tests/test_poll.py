# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eduseed_pipeline.poll import (  # noqa: E402
    extract_terminal, verify_ledger, wait_task,
)


class FakePlatform:
    """按脚本返回状态序列，不 sleep、不联网。"""

    def __init__(self, states, submissions=None, raise_on=None):
        self.states = list(states)
        self.calls = 0
        self.submissions = submissions or []
        self.raise_on = raise_on or set()
        self.list_calls = 0

    def get_task(self, task_id):
        self.calls += 1
        if self.calls in self.raise_on:
            raise RuntimeError("network hiccup")
        idx = min(self.calls - 1, len(self.states) - 1)
        state = self.states[idx]
        return {"task_id": task_id, "status": state,
                "result": {"submissionId": "sub-x", "pendingReview": True}
                if state == "completed" else {}}

    def list_my_submissions(self):
        self.list_calls += 1
        return self.submissions[self.list_calls - 1] if self.list_calls <= len(self.submissions) else []


class TestWaitTask(unittest.TestCase):
    def test_returns_on_terminal(self):
        plat = FakePlatform(["pending", "processing", "completed"])
        final, history = wait_task(plat, "t1", sleep=lambda s: None)
        self.assertEqual(final["status"], "completed")
        self.assertEqual(len(history), 3)

    def test_failed_is_terminal(self):
        plat = FakePlatform(["pending", "failed"])
        final, _ = wait_task(plat, "t1", sleep=lambda s: None)
        self.assertEqual(final["status"], "failed")

    def test_single_tick_transient_error_survives(self):
        plat = FakePlatform(["completed"], raise_on={1})
        final, history = wait_task(plat, "t1", sleep=lambda s: None)
        self.assertEqual(final["status"], "completed")
        self.assertIn("error", history[0])

    def test_timeout_does_not_raise(self):
        plat = FakePlatform(["pending"])
        final, history = wait_task(plat, "t1", timeout=0, sleep=lambda s: None)
        self.assertEqual(final["status"], "pending")
        self.assertTrue(history)

    def test_on_tick_called_per_state(self):
        seen = []
        plat = FakePlatform(["pending", "completed"])
        wait_task(plat, "t1", sleep=lambda s: None, on_tick=seen.append)
        self.assertEqual(seen, ["pending", "completed"])


class TestExtract(unittest.TestCase):
    def test_reads_nested_result(self):
        info = extract_terminal({"task_id": "t", "status": "completed",
                                 "result": {"submissionId": "sub-9", "pendingReview": True}})
        self.assertEqual(info["submission_id"], "sub-9")
        self.assertTrue(info["pending_review"])

    def test_reads_flat_shape(self):
        info = extract_terminal({"status": "completed", "submission_id": "sub-2", "id": "t2"})
        self.assertEqual(info["submission_id"], "sub-2")
        self.assertEqual(info["task_id"], "t2")

    def test_non_dict_safe(self):
        self.assertEqual(extract_terminal(None), {})


class TestVerifyLedger(unittest.TestCase):
    def test_found_on_third_attempt(self):
        # C9 真实经历：前两次查不到，第三次才有
        plat = FakePlatform(["completed"], submissions=[
            [], [],
            [{"challenge_id": "ch-1", "submission_id": "sub-1", "task_state": "submitted"}],
        ])
        res = verify_ledger(plat, "ch-1", attempts=4, interval=0, sleep=lambda s: None)
        self.assertTrue(res["found"])
        self.assertEqual(res["attempts"], 3)
        self.assertEqual(res["submission"]["submission_id"], "sub-1")

    def test_not_found_records_all_snapshots(self):
        plat = FakePlatform(["completed"], submissions=[[], [], [], []])
        res = verify_ledger(plat, "ch-1", attempts=4, interval=0, sleep=lambda s: None)
        self.assertFalse(res["found"])
        self.assertEqual(len(res["snapshots"]), 4)

    def test_exact_submission_id_preferred(self):
        plat = FakePlatform(["completed"], submissions=[[
            {"challenge_id": "ch-1", "submission_id": "old", "submitted_at": "2026-11-03T07:00:00"},
            {"challenge_id": "ch-1", "submission_id": "new", "submitted_at": "2026-11-03T12:00:00"},
        ]])
        res = verify_ledger(plat, "ch-1", expect_submission_id="new",
                            attempts=1, interval=0, sleep=lambda s: None)
        self.assertTrue(res["found"])
        self.assertEqual(res["submission"]["submission_id"], "new")

    def test_latest_used_when_no_expectation(self):
        plat = FakePlatform(["completed"], submissions=[[
            {"challenge_id": "ch-1", "submission_id": "old", "submitted_at": "2026-11-03T07:00:00"},
            {"challenge_id": "ch-1", "submission_id": "new", "submitted_at": "2026-11-03T12:00:00"},
        ]])
        res = verify_ledger(plat, "ch-1", attempts=1, interval=0, sleep=lambda s: None)
        self.assertEqual(res["submission"]["submission_id"], "new")

    def test_other_challenge_not_counted(self):
        plat = FakePlatform(["completed"], submissions=[[
            {"challenge_id": "ch-other", "submission_id": "sub-o"},
        ]])
        res = verify_ledger(plat, "ch-1", attempts=2, interval=0, sleep=lambda s: None)
        self.assertFalse(res["found"])

    def test_list_error_kept_in_snapshot(self):
        class Boom(FakePlatform):
            def list_my_submissions(self):
                raise RuntimeError("timeout")
        res = verify_ledger(Boom(["completed"]), "ch-1", attempts=2, interval=0,
                            sleep=lambda s: None)
        self.assertFalse(res["found"])
        self.assertIn("error", res["snapshots"][0])


if __name__ == "__main__":
    unittest.main()
