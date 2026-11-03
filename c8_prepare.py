"""C8 平台预检：prepare-submission。"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from eduseed_pipeline.platform import Platform, PlatformError

CHALLENGE = "ch-20260717031544-7vw0rn"
REPO = "https://github.com/ZayneWenner/C8-EduSeed-Pipeline"
TITLE = "C8 真实项目落地：EduSeed 交付流水线 eduseed-pipeline"
WORKDIR = HERE
DELIVERABLES = "*proposal*,*AAR_W*,*AI日志*,*拿来说明*"

pf = Platform()
try:
    res = pf.prepare_submission(CHALLENGE, REPO, workdir=WORKDIR,
                                required_deliverables=DELIVERABLES,
                                project_title=TITLE)
except PlatformError as exc:
    print("PLATFORM_ERROR:", exc.command, str(exc)[:600])
    sys.exit(1)

print(json.dumps(res, ensure_ascii=False, indent=1)[:4000])
with io.open(os.path.join(HERE, "..", "c8_prepare_out.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=1)

data = res
if isinstance(data, dict) and "ok" in data and isinstance(data.get("json"), dict):
    data = data["json"]
print("\nready:", data.get("ready"))
print("missing:", data.get("missing"))
print("found:", data.get("found"))
print("totalFiles:", data.get("totalFiles"))
print("actionItems:", data.get("actionItems"))
