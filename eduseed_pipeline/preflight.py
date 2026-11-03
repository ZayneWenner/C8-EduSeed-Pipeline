# -*- coding: utf-8 -*-
"""本地预检：在真正调用平台之前，先把「注定被拒」的情况挡下来。

为什么需要它：平台的 prepare-submission 会给出 missing 列表，但每次都要
单独写一个 cXd_preflight.py 去调、去解析、去人眼看 JSON。125 行像 6 份，
其中 90% 是重复的模板代码。

本模块只做纯本地计算（给定目录 + 模式 -> 命中/缺失），把平台调用留给
上一层，所以可以完全离线、可以单元测试。
"""

import os

from .patterns import PatternMatcher, diagnose_missing

# 不参与交付物判定的路径：版本库元数据、依赖缓存、编译产物
IGNORE_DIRS = {".git", ".github", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode"}
IGNORE_SUFFIX = {".pyc", ".pyo"}


def scan_files(root, max_depth=6):
    """递归列出 root 下的文件，返回相对路径（/ 分隔，稳定排序）。

    只做「有哪些文件」，不做内容判定——判定的唯一权威是 PatternMatcher。
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise NotADirectoryError(root)
    out = []
    base_depth = root.rstrip("\\/").count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.rstrip("\\/").count(os.sep) - base_depth
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS)
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() in IGNORE_SUFFIX:
                continue
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(out)


def root_files(files):
    """只保留仓库根目录层级（无 / ）的文件名。平台按根目录找交付物。"""
    return [f for f in files if "/" not in f]


def evaluate(directory, patterns, scope="root"):
    """本地判定交付物命中情况。

    scope="root" 只认根目录文件（平台真实行为）；scope="any" 全目录匹配，
    用于排查「文件其实在，只是放错目录」。
    """
    files = scan_files(directory)
    candidates = root_files(files) if scope == "root" else files
    matcher = PatternMatcher(patterns)
    judged = matcher.judge(candidates)

    diagnostics = []
    for pattern in judged["missed"]:
        hint = diagnose_missing(candidates, pattern)
        if hint:
            diagnostics.append({"pattern": pattern, **hint})

    # 放错目录的提醒：模式在子目录能命中，但在根目录不行
    misplaced = []
    if scope == "root":
        sub = [f for f in files if "/" in f]
        sub_matcher = PatternMatcher(patterns)
        for pattern in judged["missed"]:
            for name in sub:
                if pattern in sub_matcher.matched_patterns(name):
                    misplaced.append({"pattern": pattern, "file": name})

    return {
        "directory": os.path.abspath(directory),
        "pattern_list": matcher.patterns,
        "candidates": candidates,
        "total_candidates": len(candidates),
        "hits": judged["hits"],
        "missing": judged["missed"],
        "ready": not judged["missed"],
        "diagnostics": diagnostics,
        "misplaced": misplaced,
    }


def render(result):
    """把 evaluate 的结果渲染成人能直接看的一段文本。"""
    lines = []
    lines.append("目录: %s" % result["directory"])
    lines.append("候选文件: %d 个（scope=%s）" % (result["total_candidates"],
                                                 "root" if "/" not in "".join(result["candidates"]) else "any"))
    lines.append("")
    for pattern, files in result["hits"].items():
        mark = "OK  " if files else "MISS"
        lines.append("[%s] %-16s %s" % (mark, pattern, ", ".join(files) if files else "—"))
    if result["missing"]:
        lines.append("")
        lines.append("缺少 %d 项交付物: %s" % (len(result["missing"]), ", ".join(result["missing"])))
    for d in result["diagnostics"]:
        lines.append("  诊断 %s: %s —— %s" % (d["pattern"], d["reason"], d["detail"]))
    for m in result["misplaced"]:
        lines.append("  位置 %s: 文件 %s 在子目录里，平台只扫根目录" % (m["pattern"], m["file"]))
    lines.append("")
    lines.append("ready=%s" % str(result["ready"]).lower())
    return "\n".join(lines)
