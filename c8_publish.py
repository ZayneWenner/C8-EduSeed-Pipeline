"""把 eduseed-pipeline 发布到 GitHub（无本地 git，走 REST API）。"""
import io
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from eduseed_pipeline.gh import GitHub, GitHubError

TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "gh_token.txt")
OWNER = "ZayneWenner"
REPO = "C8-EduSeed-Pipeline"
DESC = "EduSeed 交付流水线：离线预检 / 载荷校验 / 任务轮询 / 台账核查（零第三方依赖）"

with io.open(TOKEN_FILE, encoding="utf-8") as fh:
    TOKEN = fh.read().strip()

gh = GitHub(token=TOKEN)
me = gh.whoami()
print("whoami:", me)

if not gh.repo_exists(OWNER, REPO):
    r = gh.create_repo(REPO, description=DESC, private=False)
    print("created:", r.get("html_url"))
else:
    print("exists:", "https://github.com/%s/%s" % (OWNER, REPO))

skip = (".git", "__pycache__", ".pytest_cache")
uploaded, failed = gh.upload_tree(OWNER, REPO, HERE, skip=skip,
                                  on_file=lambda p, ok: None)
print("uploaded=%d failed=%d" % (len(uploaded), len(failed)))
for f in failed:
    print("  FAIL", f["path"], f["error"])

# 回读核对：本地字节数 vs 远端
print("\n-- verify --")
mismatch = 0
for rel in sorted(uploaded):
    local = os.path.getsize(os.path.join(HERE, rel.replace("/", os.sep)))
    try:
        meta = gh._request("GET", "/repos/%s/%s/contents/%s"
                           % (OWNER, REPO, urllib.parse.quote(rel)))
        remote = meta.get("size")
    except GitHubError as exc:
        print("  MISS", rel, exc.status)
        mismatch += 1
        continue
    if remote != local:
        print("  DIFF", rel, "local=%d remote=%s" % (local, remote))
        mismatch += 1
print("mismatch=%d" % mismatch)

print("\nURL https://github.com/%s/%s" % (OWNER, REPO))
json.dump({"uploaded": uploaded, "failed": failed, "mismatch": mismatch,
           "url": "https://github.com/%s/%s" % (OWNER, REPO)},
          io.open(os.path.join(HERE, "..", "c8_publish_out.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
