# -*- coding: utf-8 -*-
"""统一进度报告：把台账 + 预检结果拼成一份可直接存档的文本。

为什么要单独一层：以前每次交完作业，进度散落在 13 个 json 里，
「我到底还差几个、哪个被打回」要靠人肉翻文件。这里一次算完。
"""

from . import ledger as ledger_mod


def build_report(ledger, preflight_result=None, note=None):
    parts = ["# EduSeed 交付进度报告", ""]
    if note:
        parts.append(note)
        parts.append("")
    parts.append("## 总览")
    parts.append("")
    parts.append("- 已覆盖挑战：%d 个" % ledger["covered"])
    parts.append("- 提交记录：%d 条" % ledger["records"])
    if ledger["duplicated_challenges"]:
        parts.append("- 存在重提：%s" % ", ".join(
            "%s（%d 条）" % (d["challenge_id"], d["records"])
            for d in ledger["duplicated_challenges"]))
    parts.append("")
    parts.append("## 状态分布")
    parts.append("")
    for state, count in sorted(ledger["latest_state_counts"].items(),
                               key=lambda kv: -kv[1]):
        parts.append("- %s：%d" % (state, count))
    parts.append("")
    parts.append("## 明细")
    parts.append("")
    parts.append("| 挑战 | 状态 | 提交编号 | 提交时间 |")
    parts.append("| --- | --- | --- | --- |")
    for item in ledger["items"]:
        parts.append("| %s | %s | %s | %s |" % (
            item["title"] or item["challenge_id"],
            item["state"],
            item["submission_id"],
            (item["submitted_at"] or "")[:19],
        ))
    if ledger.get("not_submitted"):
        parts.append("")
        parts.append("## 尚未提交")
        parts.append("")
        for item in ledger["not_submitted"]:
            parts.append("- %s（%s）" % (item["title"] or item["challenge_id"],
                                        item["challenge_id"]))
    if preflight_result:
        parts.append("")
        parts.append("## 本次预检")
        parts.append("")
        parts.append("- 结论：%s" % ("通过" if preflight_result["ready"] else "未通过"))
        parts.append("- 抽样文件数：%d" % len(preflight_result["files"]))
        for item in preflight_result["judged"]:
            parts.append("- %s：%s" % (
                item["pattern"],
                "已命中 " + "、".join(item["matched"]) if item["satisfied"] else "缺失"))
        for note_item in preflight_result.get("hints", []):
            parts.append("- 提示：%s" % note_item)
    return "\n".join(parts) + "\n"


def summarize_states(submissions):
    """只回答「待评审几个 / 打回几个」，供 CLI 单行输出。"""
    led = ledger_mod.build_ledger(submissions)
    return led["latest_state_counts"]
