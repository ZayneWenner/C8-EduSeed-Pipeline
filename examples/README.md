# 预检示例：跑一遍就能看到「放错目录」和「名字被拆开」两种真实事故

```bash
cd examples
python -m eduseed_pipeline.cli check --dir demo --patterns "*proposal*,*AAR_W*,*AI日志*"
```

`demo/` 的构造是刻意让它不通过的：

```
demo/
  贾静文_C8_proposal_演示.md      # 命中 *proposal*
  docs/
    贾静文_C8_AAR_W_演示.md       # 在子目录，根目录口径不算 -> 报「放错目录」
  AI协作日志.md                   # 「AI日志」被「协作」拆开 -> 报「未连续出现」
```

预期输出要点：

- `ready=false`
- `missing = ["*AAR_W*", "*AI日志*"]`
- `misplaced` 里出现 `docs/贾静文_C8_AAR_W_演示.md`
- `diagnostics` 里出现 `关键字符被拆开，未连续出现`

这正是 C1、C2 两次真实翻车的形态：文件都在，平台就是不认。
本地先看见，比等平台返回 failed 再猜要省几十秒。
