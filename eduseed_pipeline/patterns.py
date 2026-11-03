# -*- coding: utf-8 -*-
"""交付物模式匹配：复刻平台 prepare-submission 的判定语义。

证据来源（全部来自真实提交记录，不是推测）：

1. C1、C2 把 AI 日志命名为 `AI协作日志.md`，平台 missing 仍为 ["*AI日志*"]；
   改名为 `AI日志.md` 后 missing 立刻变空。
   => `*X*` 匹配的是**连续子串**，不是「分散出现」。
2. `README.md`、`paper.tex`、`references.bib` 这类无通配符的模式按整名匹配。
3. 模式串用英文逗号分隔，实际返回里也可能出现顿号/分号，故一并兼容。
4. 大小写：平台对 `README.md` 是精确名，本实现统一按不区分大小写处理，
   这是**比平台更宽松**的选择，用于本地预检以避免误报（宁可本地过、
   平台拒，也不要本地误报卡住自己）。宽松点写在 docstring 里，不藏着。

匹配对象是文件名（basename），因为平台要求交付物位于仓库根目录。
"""

import os
import re

_SPLIT = re.compile(r"[,，、;；\s]+")


def normalize_patterns(raw):
    """把平台给的模式串/列表规范成模式列表，保持原顺序。

    >>> normalize_patterns("README.md,*AI日志*,*AAR*")
    ['README.md', '*AI日志*', '*AAR*']
    >>> normalize_patterns("")
    []
    """
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        parts = [str(p) for p in raw]
    else:
        parts = _SPLIT.split(str(raw))
    out = []
    seen = set()
    for p in parts:
        p = p.strip()
        # 只由通配符构成的模式（如 "*"）不约束任何东西：留着会让"未命中"变成
        # 永远消不掉的红条，也会让 judge 得到假命中，直接丢掉。
        if p and _core(p) and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def pattern_to_regex(pattern):
    """`*` -> `.*`，其余字符全部转义，整体锚定。"""
    buf = []
    for ch in pattern:
        buf.append(".*" if ch == "*" else re.escape(ch))
    return re.compile("^" + "".join(buf) + "$", re.IGNORECASE)


def _core(pattern):
    """去掉通配符后的核心字面量，用于近似诊断。"""
    return pattern.replace("*", "")


def _is_subsequence(needle, haystack):
    """needle 的字符是否按顺序出现在 haystack 中（允许不连续）。"""
    it = iter(haystack)
    return all(ch in it for ch in needle)


class PatternMatcher:
    """按平台语义判定一组文件名命中了哪些交付物模式。"""

    def __init__(self, patterns):
        self.patterns = normalize_patterns(patterns)
        self._regex = {p: pattern_to_regex(p) for p in self.patterns}

    def matched_patterns(self, filename):
        """该文件名命中的模式列表（保持模式顺序）。"""
        base = os.path.basename(filename)
        return [p for p in self.patterns if self._regex[p].match(base)]

    def judge(self, filenames):
        """返回 {"hits": {pattern: [file...]}, "missed": [pattern...]}。"""
        hits = {p: [] for p in self.patterns}
        for name in filenames:
            for p in self.matched_patterns(name):
                hits[p].append(os.path.basename(name))
        missed = [p for p in self.patterns if not hits[p]]
        return {"hits": hits, "missed": missed}

    def is_complete(self, filenames):
        return not self.judge(filenames)["missed"]


_CJK = re.compile(u"[\u4e00-\u9fff]")
_ASCII_NAME = re.compile(r"^[\x20-\x7e]+$")


def diagnose_missing(filenames, pattern):
    """给一个未命中的模式猜最可能的原因。

    真实事故：文件名把模式里的字**拆开**了（AI协作日志 vs AI日志），
    模式本身永远不会命中，但人眼完全看不出来。这里专门抓这一类。
    返回 None 表示没找到可信解释——不硬编一个理由。
    """
    core = _core(pattern)
    if not core:
        return None
    if not filenames:
        return {
            "file": None,
            "reason": "目录为空，没有任何候选文件",
            "detail": "模式 %r 需要至少一个文件才能命中，当前扫描结果为空" % pattern,
        }
    core_lower = core.lower()
    for name in filenames:
        base = os.path.basename(name)
        low = base.lower()
        if core_lower in low:
            # 字面量其实在，说明不是内容问题，而是模式更严格（比如带扩展名）
            exact = pattern.lower()
            if not exact.endswith(low) and not low.endswith(exact):
                return {
                    "file": base,
                    "reason": "字面量存在但不满足整名/后缀约束",
                    "detail": "模式 %r 要求整名匹配，而 %r 只有中间片段相同" % (pattern, base),
                }
            return None
        if _is_subsequence(core_lower, low):
            return {
                "file": base,
                "reason": "关键字符被拆开，未连续出现",
                "detail": "模式 %r 要求 %r 连续出现；%r 里的字符被其他字分隔"
                          % (pattern, core, base),
            }
    # 中文模式 + 全英文文件名：真实事故里交付物叫 README.md / AI_LOG.md，
    # 平台按文件名匹配，怎么放都不会命中，需要点名是命名问题。
    if _CJK.search(core) and all(_ASCII_NAME.match(os.path.basename(n)) for n in filenames):
        names = [os.path.basename(n) for n in filenames]
        return {
            "file": None,
            "reason": "候选文件全是英文名，模式要求中文关键词",
            "detail": "模式 %r 要求文件名含 %r；现有文件（%s）里没有任何中文片段。"
                      "平台按文件名匹配，英文命名不会命中，请改成中文名。"
                      % (pattern, core, "、".join(names[:5])),
        }
    return None
