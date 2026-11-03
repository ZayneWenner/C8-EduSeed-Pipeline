# -*- coding: utf-8 -*-
"""eduseed-pipeline：EduSeed 课程交付流水线。

把「预检 → 发布 → 提交 → 轮询 → 台账」这套每次作业都要重写一遍的流程
收成一个可复用、可测试、零第三方依赖的工具。

设计前提全部来自真实事故，不来自猜测，详见 README 与 AI日志。
"""

__version__ = "0.1.0"

from .patterns import normalize_patterns, PatternMatcher, diagnose_missing
from .preflight import scan_files, evaluate

__all__ = [
    "normalize_patterns",
    "PatternMatcher",
    "diagnose_missing",
    "scan_files",
    "evaluate",
]
