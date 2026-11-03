# -*- coding: utf-8 -*-
"""提交台账：把「我到底交了哪些、卡在哪个状态」变成可计算的东西。

真实动机：做到第 13 份时，人已经记不住哪份交过、哪份被打回。
C5 被打回（needs_revision）后重提，旧记录仍留在列表里，
导致「同一个挑战两条记录」——统计口径一旦按记录数算就会重复计数。

所以台账按 **challenge_id 去重**，同一挑战取最新一条，并显式暴露
「一个挑战多条记录」这个事实，而不是悄悄取一条了事。
"""

import json
from datetime import datetime


def _parse_time(text):
    if not text:
        return datetime.min
    raw = str(text).replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return datetime.min


def index_by_challenge(submissions):
    """按 challenge_id 归组，组内按提交时间升序。"""
    groups = {}
    for sub in submissions:
        cid = sub.get("challenge_id")
        if not cid:
            continue
        groups.setdefault(cid, []).append(sub)
    for cid in groups:
        groups[cid].sort(key=lambda s: _parse_time(s.get("submitted_at")))
    return groups


REVIEW_STATES = {"pending_teacher_review", "checked", "submitted", "pending",
                 "needs_revision", "rejected", "completed"}


def build_ledger(submissions, challenges=None):
    """生成台账。

    返回字段刻意区分三种「数量」，因为混用会骗自己：
    - records：列表里的记录条数（含重提产生的重复）
    - covered：真正覆盖的挑战数（按 challenge_id 去重）
    - latest_states：去重后每个挑战的最新状态分布
    """
    groups = index_by_challenge(submissions)
    latest = {cid: items[-1] for cid, items in groups.items()}
    state_counts = {}
    for sub in latest.values():
        state = sub.get("task_state") or sub.get("status") or "unknown"
        state_counts[state] = state_counts.get(state, 0) + 1

    ledger = {
        "records": len(submissions),
        "covered": len(groups),
        "duplicated_challenges": sorted(
            [{"challenge_id": cid, "records": len(items),
              "submission_ids": [s.get("submission_id") for s in items]}
             for cid, items in groups.items() if len(items) > 1],
            key=lambda x: -x["records"],
        ),
        "latest_state_counts": state_counts,
        "items": [],
    }

    title_map = {}
    for ch in challenges or []:
        title_map[ch.get("challenge_id")] = ch.get("title")

    for cid, sub in sorted(latest.items(), key=lambda kv: _parse_time(kv[1].get("submitted_at"))):
        ledger["items"].append({
            "challenge_id": cid,
            "title": title_map.get(cid) or sub.get("project_title"),
            "submission_id": sub.get("submission_id"),
            "state": sub.get("task_state") or sub.get("status"),
            "submitted_at": sub.get("submitted_at"),
            "repo": sub.get("github_repo_url"),
            "records_for_challenge": len(groups[cid]),
        })

    if challenges:
        done = set(groups)
        ledger["not_submitted"] = [
            {"challenge_id": ch.get("challenge_id"), "title": ch.get("title")}
            for ch in challenges if ch.get("challenge_id") not in done
        ]
    return ledger


def render(ledger):
    lines = ["已覆盖挑战 %d 个 / 记录 %d 条" % (ledger["covered"], ledger["records"])]
    if ledger["duplicated_challenges"]:
        lines.append("存在重提的挑战: %s" % ", ".join(
            "%s×%d" % (d["challenge_id"], d["records"]) for d in ledger["duplicated_challenges"]))
    lines.append("")
    lines.append("%-26s %-22s %-26s %s" % ("挑战", "状态", "提交编号", "时间"))
    for item in ledger["items"]:
        lines.append("%-26s %-22s %-26s %s" % (
            (item["title"] or item["challenge_id"])[:24],
            str(item["state"])[:20],
            str(item["submission_id"])[:24],
            str(item["submitted_at"] or "")[:19],
        ))
    if ledger.get("not_submitted"):
        lines.append("")
        lines.append("尚未提交 %d 个: %s" % (
            len(ledger["not_submitted"]),
            ", ".join(x["title"] or x["challenge_id"] for x in ledger["not_submitted"])))
    return "\n".join(lines)


def to_json(ledger, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=1)
    return path
