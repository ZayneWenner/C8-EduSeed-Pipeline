# EduSeed 交付流水线（eduseed-pipeline）

把我在 13 次 EduSeed 挑战提交里写下的 26 个一次性脚本，收敛成一个可测试、零第三方依赖的 Python 库。
它只管四件事：**离线预检、提交载荷校验、任务轮询、提交台账核查**。

- 版本：0.1.0
- 依赖：仅 Python 3.7+ 标准库（`urllib` / `subprocess` / `json` / `re` / `pathlib`）
- 平台调用：复用已有的 `eduseed_call.py` 子进程桥，不自造 HTTP 客户端

## 为什么值得做

13 次提交踩出来 7 个坑，全部是「平台不会提前告诉你、失败还要等几十秒」的类型：

| 坑 | 后果 | 本库的对策 |
| --- | --- | --- |
| 交付物模式 `*AI日志*` 要求「AI日志」**连续**出现 | `AI协作日志.md` 不命中（C1、C2 各挂一次） | 预检用同一套连续子串语义，命中失败时给诊断 |
| 英文名 `README.md` / `AI_LOG.md` 不命中中文模式 | 文件在仓库里，平台判缺失 | 检出「中文模式 + 全英文文件名」并点名 |
| 仓库根目录之外的文件不算 | 放 `docs/` 下，本地以为齐了 | 默认 `scope=root`，并额外报告「放错目录」 |
| 插件只校验 5 个字段，服务端还硬要「项目简介」 | 返回 `ok=true` + `task_id`，任务随后 failed，真因只在 `get-task` 里 | 载荷必填 6 项，缺 `projectSummary` 直接拒绝发送 |
| 同一挑战被打回重提会留下两条记录 | 台账按记录数统计，进度虚高 | 按 `challenge_id` 去重，同时显式报告重复 |
| 提交后立刻查列表常常查不到 | C9 要第 3 次才出现；C5 曾误判「平台没入账」 | 按状态轮询、多次核查、保留每次快照 |
| 提交任务用固定 sleep 等 | 快的 0 秒（C9）、慢的 90 秒（C6），固定等待要么空转要么超时 | 按状态轮询 + 超时返回最后一次结果而不抛异常 |

## 四个命令

```bash
# 1) 离线预检：不发网络请求，只比对本地文件名与平台交付物模式
python -m eduseed_pipeline.cli check --dir . --patterns "*proposal*,*AAR_W*,*AI日志*,*拿来说明*"

# 2) 台账：合并提交记录与挑战列表，算进度、去重、列未提交
python -m eduseed_pipeline.cli status

# 3) 报告：台账 + 预检结果合成一份可存档的 Markdown
python -m eduseed_pipeline.cli report --dir . --patterns "*proposal*,*AAR_W*" --out REPORT.md

# 4) 提交：校验载荷 → 提交 → 轮询至终态 → 核查是否入账
python -m eduseed_pipeline.cli submit --dir . \
  --challenge-id ch-xxx --repo-url https://github.com/ZayneWenner/xxx \
  --title "项目名" --summary "项目简介（≥60 字）" \
  --aar-file AAR.md --self-eval-file 自评.md
```

退出码：`0` 正常、`1` 预检未通过、`6` 平台调用失败、`7` 文件缺失。
失败一律打印「下一步该干什么」，不抛裸 traceback。

## 三个刻意的设计取舍

**1. 本地匹配比平台宽（大小写不敏感）。**
平台是精确匹配。本地做宽松判断，是为了宁可多放行、也不要在本地制造假阴性——
否则我会去改一个本来没问题的文件名，把仓库弄乱。代价是本地 `ready=true` 不保证平台通过，
所以 `submit` 之后必须跑一次真实预检（`prepare-submission`）作为最终口径。

**2. 只由通配符构成的模式（`*`）直接丢弃。**
它不约束任何东西。留着会让「未命中」变成永远消不掉的红条，也会让 `judge` 得到假命中。

**3. 轮询超时返回最后一次结果，不抛异常。**
超时是信息（「还在跑」），不是错误。抛异常会让我误以为提交失败而重复提交——那才是真事故。

## 目录

```
eduseed_pipeline/
  patterns.py   交付物模式 → 正则、连续子串判定、失败诊断
  preflight.py  目录扫描（含忽略规则）、根目录/全目录两种口径
  platform.py   子进程调用平台，统一错误类型
  submit.py     载荷构建与 6 项必填校验、失败原因翻译
  poll.py       任务轮询、入账核查
  ledger.py     提交台账：去重、进度、重复挑战
  report.py     报告生成
  gh.py         GitHub REST（建仓/上传/Pages），纯 urllib
  cli.py        命令行入口
tests/          66 个用例，全部对应真实事故
examples/       一个可直接跑的预检示例
```

## 测试

```bash
python -m unittest discover -s tests -v
```

66 个用例，覆盖连续子串、中文标点分割、忽略目录、放错目录、载荷缺字段、
轮询超时、入账延迟与重复记录。**不为覆盖率凑数**——每条都对应一次真实踩坑。

## 边界

- 不做账号登录、不存凭据；GitHub 令牌只从环境变量 `GITHUB_TOKEN` 读。
- 不判定评审结果，也不生成学习内容——它只保证「材料齐、提交成功、入账可查」。
- 平台接口字段若变更，`platform.py` 的 `PlatformError` 会带原始响应，便于定位。
