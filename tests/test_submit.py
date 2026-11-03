# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eduseed_pipeline.submit import (  # noqa: E402
    PayloadError, build_payload, explain_failure, validate_payload,
)

GOOD = {
    "challengeId": "ch-20260717031544-7vw0rn",
    "githubRepoUrl": "https://github.com/ZayneWenner/C8-Project",
    "projectTitle": "EduSeed 交付流水线",
    "projectSummary": "把 26 个一次性脚本收敛成一个可测试的 Python 库，"
                      "覆盖离线预检、提交载荷校验、任务轮询、台账核查四段，"
                      "零第三方依赖，每条规则都对应一次真实踩坑。",
    "aarText": "A" * 260,
    "selfEvaluationText": "S" * 60,
}


class TestValidate(unittest.TestCase):
    def test_good_payload_passes(self):
        self.assertEqual(validate_payload(GOOD), [])

    def test_missing_project_summary_is_caught(self):
        # 最高代价的一条：插件不校验、服务端硬卡，漏了就静默失败
        bad = {k: v for k, v in GOOD.items() if k != "projectSummary"}
        problems = validate_payload(bad)
        self.assertTrue(any("projectSummary" in p for p in problems))

    def test_blank_string_treated_as_missing(self):
        bad = dict(GOOD, projectSummary="   ")
        self.assertTrue(any("projectSummary" in p for p in validate_payload(bad)))

    def test_short_summary_rejected(self):
        bad = dict(GOOD, projectSummary="太短")
        self.assertTrue(any("过短" in p for p in validate_payload(bad)))

    def test_non_string_field_rejected(self):
        bad = dict(GOOD, projectTitle=12345)
        self.assertTrue(any("应为字符串" in p for p in validate_payload(bad)))

    def test_non_github_url_rejected(self):
        bad = dict(GOOD, githubRepoUrl="https://gitlab.com/x/y")
        self.assertTrue(any("github.com" in p for p in validate_payload(bad)))

    def test_all_missing_reports_each_field(self):
        problems = validate_payload({})
        self.assertEqual(len(problems), 6)


class TestBuild(unittest.TestCase):
    def test_build_returns_all_required(self):
        payload = build_payload(
            challenge_id=GOOD["challengeId"], repo_url=GOOD["githubRepoUrl"],
            project_title=GOOD["projectTitle"], project_summary=GOOD["projectSummary"],
            aar_text=GOOD["aarText"], self_evaluation_text=GOOD["selfEvaluationText"])
        self.assertEqual(set(payload), set(GOOD))

    def test_build_raises_with_problem_list(self):
        with self.assertRaises(PayloadError) as ctx:
            build_payload("ch-x", GOOD["githubRepoUrl"], GOOD["projectTitle"],
                          "", GOOD["aarText"], GOOD["selfEvaluationText"])
        self.assertTrue(ctx.exception.problems)

    def test_extra_merged(self):
        payload = build_payload(
            GOOD["challengeId"], GOOD["githubRepoUrl"], GOOD["projectTitle"],
            GOOD["projectSummary"], GOOD["aarText"], GOOD["selfEvaluationText"],
            extra={"selfEvaluationLevel": 3})
        self.assertEqual(payload["selfEvaluationLevel"], 3)


class TestExplain(unittest.TestCase):
    def test_explains_project_summary_failure(self):
        out = explain_failure({"status": "failed",
                               "result": {"error": "缺少必填项：项目简介"}})
        self.assertIn("projectSummary", out["hint"])

    def test_explains_github_failure(self):
        out = explain_failure({"status": "failed", "error": "GitHub 未绑定"})
        self.assertIn("GitHub", out["hint"])

    def test_completed_has_no_reason(self):
        self.assertIsNone(explain_failure({"status": "completed"})["reason"])

    def test_unknown_error_preserves_text(self):
        out = explain_failure({"status": "failed", "error": "某个新错误"})
        self.assertEqual(out["reason"], "某个新错误")


if __name__ == "__main__":
    unittest.main()
