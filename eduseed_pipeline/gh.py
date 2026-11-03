# -*- coding: utf-8 -*-
"""GitHub 发布层：在没有本地 git 的机器上也能建仓库、上传文件、开 Pages。

真实背景：这台机器上 git/gh 曾经失效（便携工具链被临时目录清理掉），
当时是靠 Windows 凭据管理器里存的 GitHub 凭据（账号 ZayneWenner）
走 REST API 完成建仓与上传的。这套路径被验证过 5 次以上，所以固化在这里。

只依赖标准库 urllib，不引入 PyGithub 之类的第三方包。
"""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
TOKEN_ENV = "GITHUB_TOKEN"


class GitHubError(RuntimeError):
    def __init__(self, status, message, url=None):
        super().__init__("GitHub %s: %s" % (status, message))
        self.status = status
        self.url = url


def token_from_env():
    tok = os.environ.get(TOKEN_ENV, "").strip()
    if not tok:
        raise GitHubError(0, "未设置环境变量 %s（不要把令牌写进代码或仓库）" % TOKEN_ENV)
    return tok


class GitHub:
    def __init__(self, token=None, opener=None):
        self._token = token or token_from_env()
        self._opener = opener or urllib.request.urlopen

    def _request(self, method, path, body=None):
        url = API + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self._token)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with self._opener(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise GitHubError(exc.code, detail, url) from None

    # --- 账号 ---
    def whoami(self):
        return self._request("GET", "/user").get("login")

    # --- 仓库 ---
    def repo_exists(self, owner, name):
        try:
            self._request("GET", "/repos/%s/%s" % (owner, name))
            return True
        except GitHubError as exc:
            if exc.status == 404:
                return False
            raise

    def create_repo(self, name, description="", private=False):
        return self._request("POST", "/user/repos", {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": True,
            "has_issues": True,
            "has_wiki": False,
        })

    # --- 文件 ---
    def get_file_sha(self, owner, name, path):
        try:
            data = self._request("GET", "/repos/%s/%s/contents/%s"
                                 % (owner, name, urllib.parse.quote(path)))
            return data.get("sha")
        except GitHubError as exc:
            if exc.status == 404:
                return None
            raise

    def put_file(self, owner, name, path, content_bytes, message=None):
        """新建或更新单个文件。已存在则先取 sha 再带 sha 更新，否则 422。"""
        sha = self.get_file_sha(owner, name, path)
        body = {
            "message": message or ("chore: sync " + path),
            "content": base64.b64encode(content_bytes).decode("ascii"),
        }
        if sha:
            body["sha"] = sha
        return self._request("PUT", "/repos/%s/%s/contents/%s"
                            % (owner, name, urllib.parse.quote(path)), body)

    def upload_tree(self, owner, name, local_root, skip=(".git", "__pycache__"),
                    on_file=None):
        """把一个目录上传到仓库根，返回 (uploaded, failed)。失败不中断整批。"""
        uploaded, failed = [], []
        for dirpath, dirnames, filenames in os.walk(local_root):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, local_root).replace(os.sep, "/")
                try:
                    with open(full, "rb") as fh:
                        self.put_file(owner, name, rel, fh.read())
                    uploaded.append(rel)
                    if on_file:
                        on_file(rel, True)
                except Exception as exc:
                    failed.append({"path": rel, "error": repr(exc)[:200]})
                    if on_file:
                        on_file(rel, False)
        return uploaded, failed

    # --- Pages ---
    def enable_pages(self, owner, name, branch="main", path="/"):
        """为仓库开 GitHub Pages。已开启时返回 409，按幂等处理不报错。"""
        try:
            return self._request("POST", "/repos/%s/%s/pages" % (owner, name), {
                "source": {"branch": branch, "path": path},
            })
        except GitHubError as exc:
            if exc.status == 409:
                return {"already_enabled": True}
            raise

    def pages_status(self, owner, name):
        try:
            return self._request("GET", "/repos/%s/%s/pages" % (owner, name))
        except GitHubError as exc:
            if exc.status == 404:
                return {"enabled": False}
            raise
