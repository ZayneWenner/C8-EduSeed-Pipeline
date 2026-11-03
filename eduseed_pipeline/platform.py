# -*- coding: utf-8 -*-
"""平台调用层：把 eduseed-course-client 的命令行协议包成函数。

真实调用链（不是推测，来自实际跑通的脚本）：
    python <eduseed_call.py> <command> '<payload_json>'
它内部再走 node run-skill.cjs，stdout 是**一行 JSON**，stderr 混着
[run-skill:secrets] 的注入日志——所以绝不能把 stderr 当错误信号，
判定只看 rc 与 stdout 能否解析。

设计上把 subprocess 抽成 runner 注入点，测试时可以塞假实现，
不需要网络就能验证上层逻辑。
"""

import json
import os
import subprocess
import sys

DEFAULT_CALL_SCRIPT = (
    r"D:\.cogseed\userWorkSpace\c-users-86178-desktop-贾静文_c4_\eduseed_call.py"
)


class PlatformError(RuntimeError):
    """平台返回 ok=false 或无法解析。"""

    def __init__(self, command, message, payload=None):
        super().__init__("[%s] %s" % (command, message))
        self.command = command
        self.payload = payload or {}


def subprocess_runner(script_path, timeout=240):
    def run(command, payload):
        proc = subprocess.run(
            [sys.executable, script_path, command, json.dumps(payload, ensure_ascii=False)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    return run


class Platform:
    """平台命令封装。所有命令返回解析后的 dict（已剥掉外层壳）。"""

    def __init__(self, runner=None, call_script=None):
        if runner is None:
            script = call_script or os.environ.get("EDUSEED_CALL_SCRIPT") or DEFAULT_CALL_SCRIPT
            if not os.path.isfile(script):
                raise FileNotFoundError(
                    "找不到平台调用脚本: %s（可用 EDUSEED_CALL_SCRIPT 覆盖）" % script
                )
            runner = subprocess_runner(script)
        self._runner = runner

    def call(self, command, payload=None, allow_error=False):
        rc, out, err = self._runner(command, payload or {})
        text = (out or "").strip()
        if not text:
            raise PlatformError(command, "stdout 为空，rc=%s，stderr 尾部=%r"
                                % (rc, (err or "")[-300:]))
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise PlatformError(command, "stdout 不是 JSON，前 300 字=%r" % text[:300])
        if isinstance(data, dict) and data.get("ok") is False and not allow_error:
            error = data.get("error")
            msg = error.get("message") if isinstance(error, dict) else str(error)
            raise PlatformError(command, msg or "ok=false", data)
        return data

    # ---- 具体命令，语义按真实返回字段命名 ----

    def list_challenges(self):
        return self.call("list-challenges").get("challenges") or []

    def prepare_submission(self, challenge_id, repo_url):
        return self.call("prepare-submission",
                         {"challengeId": challenge_id, "githubRepoUrl": repo_url})

    def submit_project(self, payload):
        return self.call("submit-project", payload)

    def get_task(self, task_id):
        return self.call("get-task", {"taskId": task_id}, allow_error=True)

    def list_my_submissions(self):
        """注意字段名是 submission_id / challenge_id。

        真实事故：C5 重提后我用错字面量去匹配字段，得出「平台没入账」的
        错误结论，差点去投诉平台。字段名必须在代码里显式写死并加注释。
        """
        return self.call("list-my-submissions").get("submissions") or []

    def get_dashboard(self):
        return self.call("get-dashboard").get("stats") or {}
