# -*- coding: utf-8 -*-
"""提交载荷构造与护栏。

真实事故（代价最高的一条）：平台插件 submit-project 的必填项只报 5 个
（challengeId / githubRepoUrl / projectTitle / aarText / selfEvaluationText），
但服务端还硬性要求「项目简介」，对应运行时字段 projectSummary。
漏掉它时插件依然返回 ok=true + task_id，任务随后 failed，
真实原因只在 get-task 的 result.error 里：「缺少必填项：项目简介」。

所以这里的护栏不是「帮用户少填几个字」，是挡住一类会让时间白花的静默失败。
"""

REQUIRED_FIELDS = (
    "challengeId",
    "githubRepoUrl",
    "projectTitle",
    "aarText",
    "selfEvaluationText",
    "projectSummary",  # 插件不校验、服务端硬卡，必须在此处强制
)

MIN_LENGTHS = {
    "projectTitle": 4,
    "aarText": 200,
    "selfEvaluationText": 50,
    "projectSummary": 60,
}


class PayloadError(ValueError):
    def __init__(self, problems):
        super().__init__("提交载荷不合格: " + "; ".join(problems))
        self.problems = problems


def validate_payload(payload):
    """返回问题列表，空列表表示可以提交。不做字段内容的润色。"""
    problems = []
    for field in REQUIRED_FIELDS:
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            problems.append("缺少必填字段 %s" % field)
            continue
        if not isinstance(value, str):
            problems.append("字段 %s 应为字符串，实际 %s" % (field, type(value).__name__))
            continue
        need = MIN_LENGTHS.get(field)
        if need and len(value.strip()) < need:
            problems.append("字段 %s 过短（%d 字，至少 %d 字）"
                            % (field, len(value.strip()), need))
    repo = payload.get("githubRepoUrl") or ""
    if repo and not repo.startswith("https://github.com/"):
        problems.append("githubRepoUrl 必须是 https://github.com/ 开头的公开仓库地址")
    return problems


def build_payload(challenge_id, repo_url, project_title, project_summary,
                  aar_text, self_evaluation_text, extra=None):
    """按平台约定拼载荷，缺字段就抛错，绝不静默补空串。"""
    payload = {
        "challengeId": challenge_id,
        "githubRepoUrl": repo_url,
        "projectTitle": project_title,
        "projectSummary": project_summary,
        "aarText": aar_text,
        "selfEvaluationText": self_evaluation_text,
    }
    if extra:
        payload.update(extra)
    problems = validate_payload(payload)
    if problems:
        raise PayloadError(problems)
    return payload


def explain_failure(task_result):
    """把 get-task 的失败结果翻译成人话，尤其针对 projectSummary 这类暗坑。"""
    if not isinstance(task_result, dict):
        return {"reason": "无法解析的任务结果", "hint": str(task_result)[:200]}
    status = task_result.get("status")
    if status == "completed":
        return {"reason": None, "hint": "已完成"}
    error = task_result.get("error") or (task_result.get("result") or {}).get("error")
    text = error if isinstance(error, str) else (error or {}).get("message", "")
    hint = ""
    if isinstance(text, str) and "项目简介" in text:
        hint = "服务端要求 projectSummary，插件不校验，补上该字段后重提"
    elif isinstance(text, str) and "GitHub" in text:
        hint = "检查账号 GitHub 绑定与仓库可见性"
    return {"reason": text or ("任务状态 %s" % status), "hint": hint}
