# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eduseed_pipeline.preflight import evaluate, root_files, scan_files  # noqa: E402


def _touch(root, rel):
    full = os.path.join(root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write("x")
    return full


class TestScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_scan_relative_paths(self):
        _touch(self.tmp, "a.md")
        _touch(self.tmp, "sub/b.md")
        files = scan_files(self.tmp)
        self.assertIn("a.md", files)
        self.assertIn("sub/b.md", files)

    def test_ignores_pycache_and_git(self):
        _touch(self.tmp, ".git/config")
        _touch(self.tmp, "pkg/__pycache__/m.pyc")
        _touch(self.tmp, "keep.md")
        files = scan_files(self.tmp)
        self.assertEqual(files, ["keep.md"])

    def test_root_files_only_top_level(self):
        _touch(self.tmp, "a.md")
        _touch(self.tmp, "sub/b.md")
        self.assertEqual(root_files(scan_files(self.tmp)), ["a.md"])


class TestEvaluate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_ready_when_all_hit(self):
        for name in ("c_proposal.md", "c_AAR_W.md"):
            _touch(self.tmp, name)
        res = evaluate(self.tmp, ["*proposal*", "*AAR_W*"])
        self.assertTrue(res["ready"])
        self.assertEqual(res["missing"], [])

    def test_not_ready_lists_missing(self):
        _touch(self.tmp, "c_proposal.md")
        res = evaluate(self.tmp, ["*proposal*", "*AAR_W*"])
        self.assertFalse(res["ready"])
        self.assertEqual(res["missing"], ["*AAR_W*"])

    def test_subdir_file_warns_as_misplaced_in_root_scope(self):
        # 真实风险：文件放进子目录，本地以为齐了，平台只看仓库根 -> 判缺失
        _touch(self.tmp, "docs/c_proposal.md")
        res = evaluate(self.tmp, ["*proposal*"], scope="root")
        self.assertFalse(res["ready"])
        self.assertTrue(res["misplaced"])
        self.assertEqual(res["misplaced"][0]["file"], "docs/c_proposal.md")

    def test_all_scope_accepts_subdir(self):
        _touch(self.tmp, "docs/c_proposal.md")
        res = evaluate(self.tmp, ["*proposal*"], scope="all")
        self.assertTrue(res["ready"])

    def test_hint_attached_for_missed(self):
        _touch(self.tmp, "AI协作日志.md")
        res = evaluate(self.tmp, ["*AI日志*"])
        self.assertTrue(any("连续" in d["reason"] for d in res["diagnostics"]))

    def test_empty_dir_not_ready(self):
        res = evaluate(self.tmp, ["*proposal*"])
        self.assertFalse(res["ready"])


if __name__ == "__main__":
    unittest.main()
