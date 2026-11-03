# -*- coding: utf-8 -*-
"""命令行入口：python -m eduseed_pipeline <command> ...

四个命令对应真实流程的四段，一段一条命令，不再写一次性脚本：
  check    本地预检（离线，最快的反馈回路）
  status   提交台账（我交了哪些、卡在哪）
  report   进度报告（台账 + 本次预检合成存档）
  submit   提交并轮询到终态，再核查入账

设计原则：任何一步失败都给出可执行的下一步，而不是抛一段 traceback。
"""

import argparse
import json
import os
import sys

from . import __version__
from . import ledger as ledger_mod
from . import poll as poll_mod
from . import report as report_mod
from . import submit as submit_mod
from .patterns import normalize_patterns
from .platform import Platform, PlatformError
from .preflight import evaluate, render


def _platform(args):
    return Platform(call_script=args.call_script) if args.call_script else Platform()


def cmd_check(args):
    patterns = normalize_patterns(args.patterns)
    result = evaluate(args.dir, patterns, scope=args.scope)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(render(result))
    return 0 if result["ready"] else 1


def cmd_status(args):
    plat = _platform(args)
    subs = plat.list_my_submissions()
    challenges = plat.list_challenges() if args.with_challenges else None
    led = ledger_mod.build_ledger(subs, challenges)
    if args.json:
        print(json.dumps(led, ensure_ascii=False, indent=1))
    else:
        print(ledger_mod.render(led))
    if args.save:
        ledger_mod.to_json(led, args.save)
    return 0


def cmd_report(args):
    plat = _platform(args)
    subs = plat.list_my_submissions()
    challenges = plat.list_challenges()
    led = ledger_mod.build_ledger(subs, challenges)
    pre = None
    if args.dir and args.patterns:
        pre = evaluate(args.dir, normalize_patterns(args.patterns), scope=args.scope)
    text = report_mod.build_report(led, pre, note=args.note)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("报告已写入 %s（覆盖 %d 个挑战）" % (args.out, led["covered"]))
    else:
        print(text)
    return 0


def cmd_submit(args):
    plat = _platform(args)

    # 1) 平台侧预检：本地 check 通过不代表平台认可，两边都要过
    print("[1/4] 平台预检 ...")
    pre = plat.prepare_submission(args.challenge, args.repo)
    missing = pre.get("missing") or []
    total = pre.get("totalFiles") or pre.get("total_files")
    if missing:
        print("      未通过，缺少交付物：%s" % ", ".join(str(m) for m in missing))
        print("      下一步：python -m eduseed_pipeline check --dir <目录> --patterns \"%s\""
              % ",".join(str(m) for m in missing))
        return 2
    print("      通过，仓库内文件 %s 个" % total)

    # 2) 载荷护栏：projectSummary 这类暗坑在这里被挡住
    print("[2/4] 校验提交载荷 ...")
    try:
        payload = submit_mod.build_payload(
            challenge_id=args.challenge,
            repo_url=args.repo,
            project_title=args.title,
            project_summary=args.summary,
            aar_text=_read_text(args.aar),
            self_evaluation_text=_read_text(args.self_eval),
        )
    except submit_mod.PayloadError as exc:
        for problem in exc.problems:
            print("      - %s" % problem)
        return 2
    print("      通过")

    # 3) 提交 + 轮询
    print("[3/4] 提交并等待平台处理 ...")
    resp = plat.submit_project(payload)
    task_id = resp.get("task_id") or resp.get("taskId")
    if not task_id:
        print("      提交未返回 task_id，原始返回：%s"
              % json.dumps(resp, ensure_ascii=False)[:400])
        return 3
    print("      task_id = %s" % task_id)
    final, history = poll_mod.wait_task(
        plat, task_id, timeout=args.timeout, interval=args.interval,
        on_tick=lambda s: print("      状态 -> %s" % s))
    info = poll_mod.extract_terminal(final)
    print("      轮询 %d 次，终态 %s" % (len(history), info.get("status")))

    if info.get("status") != "completed":
        explained = submit_mod.explain_failure(final)
        print("      失败原因：%s" % explained["reason"])
        if explained["hint"]:
            print("      提示：%s" % explained["hint"])
        return 4
    print("      submission_id = %s，待评审 = %s"
          % (info.get("submission_id"), info.get("pending_review")))

    # 4) 入账核查：提交成功不等于列表里有，必须查
    print("[4/4] 核查入账 ...")
    check = poll_mod.verify_ledger(
        plat, args.challenge, expect_submission_id=info.get("submission_id"),
        attempts=args.verify_attempts, interval=args.verify_interval)
    for snap in check["snapshots"]:
        print("      第 %d 次：记录总数 %s，本挑战命中 %s"
              % (snap.get("attempt"), snap.get("total", "-"), snap.get("challenge_hits", "-")))
    if check["found"]:
        print("      已入账，状态 %s" % check["submission"].get("task_state"))
        return 0
    print("      未查到记录。注意：这不等于平台未入账——"
          "列表有延迟，也可能是字段名判断问题。")
    print("      保留证据后可稍后复查：python -m eduseed_pipeline status")
    return 5


def _read_text(path):
    if not path:
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="eduseed_pipeline",
        description="EduSeed 课程交付流水线：预检 -> 提交 -> 轮询 -> 台账")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--call-script", dest="call_script", default=None,
                        help="平台调用脚本路径（默认取内置约定路径）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="本地预检交付物模式")
    p_check.add_argument("--dir", required=True)
    p_check.add_argument("--patterns", required=True,
                         help="逗号分隔，如 \"*proposal*,*AAR_W*,*AI日志*\"")
    p_check.add_argument("--scope", default="root", choices=["root", "all"])
    p_check.set_defaults(func=cmd_check)

    p_status = sub.add_parser("status", help="查看提交台账")
    p_status.add_argument("--with-challenges", action="store_true",
                          help="同时拉取挑战清单，算出尚未提交的挑战")
    p_status.add_argument("--save", default=None, help="把台账另存为 JSON")
    p_status.set_defaults(func=cmd_status)

    p_report = sub.add_parser("report", help="生成进度报告")
    p_report.add_argument("--dir", default=None)
    p_report.add_argument("--patterns", default=None)
    p_report.add_argument("--scope", default="root", choices=["root", "all"])
    p_report.add_argument("--out", default=None)
    p_report.add_argument("--note", default=None)
    p_report.set_defaults(func=cmd_report)

    p_submit = sub.add_parser("submit", help="提交并轮询至终态")
    p_submit.add_argument("--challenge", required=True)
    p_submit.add_argument("--repo", required=True)
    p_submit.add_argument("--title", required=True)
    p_submit.add_argument("--summary", required=True)
    p_submit.add_argument("--aar", required=True, help="AAR 文本文件路径")
    p_submit.add_argument("--self-eval", dest="self_eval", required=True,
                          help="自评文本文件路径")
    p_submit.add_argument("--timeout", type=int, default=300)
    p_submit.add_argument("--interval", type=int, default=5)
    p_submit.add_argument("--verify-attempts", dest="verify_attempts", type=int, default=4)
    p_submit.add_argument("--verify-interval", dest="verify_interval", type=int, default=20)
    p_submit.set_defaults(func=cmd_submit)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except PlatformError as exc:
        print("平台调用失败（%s）：%s" % (exc.command, exc))
        if exc.payload:
            print("原始返回：%s" % json.dumps(exc.payload, ensure_ascii=False)[:400])
        return 6
    except FileNotFoundError as exc:
        print("找不到文件：%s" % exc)
        return 7


if __name__ == "__main__":
    sys.exit(main())
