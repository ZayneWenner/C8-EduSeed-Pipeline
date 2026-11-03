# -*- coding: utf-8 -*-
"""任务轮询与入账核查。

两个真实坑，都在这里被固化下来：

1. submit-project 立刻返回 task_id，但 get-task 初始是 pending。
   不同挑战耗时差很大：C4D 约 35 秒、C6 约 90 秒、C9 首轮即 completed。
   固定 sleep 是错的，必须按状态轮询并设上限。

2. 查列表要用正确字段名 submission_id，且**有延迟**。
   C9 第一次查没有记录，第二次也没有，第三次才有；C5 那次我误判成
   「平台没入账」，实际是脚本字段名写错。所以核查必须：
   (a) 显式读 submission_id/challenge_id；
   (b) 允许多次重试并记录每次的计数，而不是查一次就下结论。
"""

import time

TERMINAL = {"completed", "failed", "cancelled", "canceled"}
GOOD = {"completed"}


def wait_task(platform, task_id, timeout=300, interval=5, sleep=time.sleep, on_tick=None):
    """轮询 get-task 直到终态或超时。返回 (终态结果, 历史)。

    超时**不算失败**：返回最后一次结果，由调用方决定后续，不抛异常掩盖信息。
    """
    history = []
    deadline = time.time() + timeout
    last = None
    while True:
        try:
            last = platform.get_task(task_id)
        except Exception as exc:  # 单次网络抖动不该终止整轮
            history.append({"t": round(time.time(), 2), "error": repr(exc)[:200]})
            last = None
        if last:
            status = last.get("status") or (last.get("task") or {}).get("status")
            history.append({"t": round(time.time(), 2), "status": status})
            if on_tick:
                on_tick(status)
            if status in TERMINAL:
                return last, history
        if time.time() >= deadline:
            return last, history
        sleep(interval)


def extract_terminal(task_result):
    """从终态结果里抽出真正要记的字段。字段名按真实返回，不做猜测性兼容。"""
    if not isinstance(task_result, dict):
        return {}
    body = task_result.get("task") if isinstance(task_result.get("task"), dict) else task_result
    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    return {
        "status": body.get("status"),
        "task_id": body.get("task_id") or body.get("id"),
        "submission_id": result.get("submissionId") or body.get("submission_id"),
        "pending_review": result.get("pendingReview"),
        "error": result.get("error") or body.get("error"),
    }


def verify_ledger(platform, challenge_id, expect_submission_id=None,
                  attempts=4, interval=20, sleep=time.sleep):
    """核查某挑战是否已进入我的提交列表。

    返回 dict：found / attempts / snapshots / submission。查不到就是查不到，
    不推断成「未提交」——把每次快照留下来，方便以后跟平台对账。
    """
    snapshots = []
    for i in range(attempts):
        try:
            subs = platform.list_my_submissions()
        except Exception as exc:
            snapshots.append({"attempt": i + 1, "error": repr(exc)[:200]})
        else:
            hits = [s for s in subs if s.get("challenge_id") == challenge_id]
            if expect_submission_id:
                exact = [s for s in hits if s.get("submission_id") == expect_submission_id]
                target = exact[0] if exact else None
            else:
                target = max(hits, key=lambda s: s.get("submitted_at") or "") if hits else None
            snapshots.append({
                "attempt": i + 1,
                "total": len(subs),
                "challenge_hits": len(hits),
                "matched": (target or {}).get("submission_id"),
            })
            if target:
                return {"found": True, "attempts": i + 1, "snapshots": snapshots,
                        "submission": target}
        if i < attempts - 1:
            sleep(interval)
    return {"found": False, "attempts": attempts, "snapshots": snapshots, "submission": None}
