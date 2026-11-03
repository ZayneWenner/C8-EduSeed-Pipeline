# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eduseed_pipeline.patterns import (  # noqa: E402
    PatternMatcher, diagnose_missing, normalize_patterns, pattern_to_regex,
)


class TestNormalize(unittest.TestCase):
    def test_splits_english_comma(self):
        self.assertEqual(normalize_patterns("*a*,*b*"), ["*a*", "*b*"])

    def test_splits_chinese_comma(self):
        # 平台清单里用的是中文逗号，C8 就是 *proposal*,*AAR_W*,*AI日志*,*拿来说明*
        self.assertEqual(normalize_patterns("*a*，*b*"), ["*a*", "*b*"])

    def test_splits_semicolon_and_space(self):
        self.assertEqual(normalize_patterns("*a*; *b*  *c*"), ["*a*", "*b*", "*c*"])

    def test_empty_items_dropped(self):
        self.assertEqual(normalize_patterns(",,*a*,"), ["*a*"])


class TestPatternSemantics(unittest.TestCase):
    """这些用例就是真实事故回放。"""

    def test_contiguous_substring_required(self):
        m = PatternMatcher(["*AI日志*"])
        # C1/C2 真实事故：名字里有「AI」和「日志」，但不连续 -> 平台判缺失
        self.assertEqual(m.matched_patterns("AI协作日志.md"), [])
        self.assertEqual(m.matched_patterns("AI日志.md"), ["*AI日志*"])

    def test_case_insensitive_locally(self):
        m = PatternMatcher(["*aar_w*"])
        self.assertEqual(m.matched_patterns("贾静文_C8_AAR_W.md"), ["*aar_w*"])

    def test_prefix_and_suffix_wildcards(self):
        m = PatternMatcher(["*demo*"])
        self.assertEqual(m.matched_patterns("demo.mp4"), ["*demo*"])
        self.assertEqual(m.matched_patterns("贾静文_C6_demo_录屏.mp4"), ["*demo*"])
        self.assertEqual(m.matched_patterns("demofile"), ["*demo*"])
        self.assertEqual(m.matched_patterns("my_demo.txt"), ["*demo*"])

    def test_all_four_c8_patterns(self):
        m = PatternMatcher(["*proposal*", "*AAR_W*", "*AI日志*", "*拿来说明*"])
        names = [
            "贾静文_C8_proposal_交付流水线.md",
            "贾静文_C8_AAR_W.md",
            "贾静文_C8_AI日志.md",
            "贾静文_C8_拿来说明.md",
        ]
        self.assertEqual(m.judge(names)["missed"], [])
        self.assertTrue(m.is_complete(names))

    def test_missing_one_pattern_reported(self):
        m = PatternMatcher(["*proposal*", "*AAR_W*"])
        verdict = m.judge(["x_proposal.md"])
        self.assertEqual(verdict["missed"], ["*AAR_W*"])
        self.assertFalse(m.is_complete(["x_proposal.md"]))

    def test_one_file_can_satisfy_two_patterns(self):
        m = PatternMatcher(["*proposal*", "*AAR*"])
        verdict = m.judge(["p_proposal_AAR.md"])
        self.assertEqual(verdict["missed"], [])

    def test_regex_escape_special_chars(self):
        m = PatternMatcher(["*(1)*"])
        self.assertEqual(m.matched_patterns("a(1)b.md"), ["*(1)*"])

    def test_empty_pattern_never_matches(self):
        m = PatternMatcher(["*"])
        self.assertEqual(m.matched_patterns("x.md"), [])

    def test_pattern_to_regex_anchored(self):
        rx = pattern_to_regex("*abc*")
        self.assertTrue(rx.search("xxabcxx"))
        self.assertFalse(rx.search("axbxc"))


class TestDiagnose(unittest.TestCase):
    def test_diagnoses_scattered_incident(self):
        hint = diagnose_missing(["AI协作日志.md"], "*AI日志*")
        self.assertIn("连续", hint["reason"])
        self.assertEqual(hint["file"], "AI协作日志.md")

    def test_diagnoses_english_filename(self):
        hint = diagnose_missing(["README.md", "AI_LOG.md"], "*AI日志*")
        self.assertTrue("中文" in hint["reason"] or "英文" in hint["reason"])

    def test_diagnoses_empty_dir(self):
        hint = diagnose_missing([], "*proposal*")
        self.assertIn("空", hint["reason"])

    def test_no_hint_when_nothing_similar(self):
        self.assertIsNone(diagnose_missing(["zzz.md"], "*proposal*"))


if __name__ == "__main__":
    unittest.main()
