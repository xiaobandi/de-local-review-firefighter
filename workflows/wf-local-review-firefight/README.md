# 差评灭火回复生成

> 根因判断 → 生成公开回复+私信补救话术+补偿方案建议

工作流 `wf-local-review-firefight`　·　归属 差评灭火官　·　触发 事件（新差评）→ **即时推送预警**　·　
复杂度 S　·　阶段 P0

## 调用链

- `回复话术生成`（reply-copy-generator）
- `差评安抚话术`（complaint-soothe）

## 文档

- [`WORKFLOW.md`](WORKFLOW.md) — 完整编排、闸门、降级与验收标准
- [`tests/cases.yaml`](tests/cases.yaml) — 端到端 / 闸门 / 降级用例

## 一句话试用

```text
帮我跑 差评灭火官 的「差评灭火回复生成」：<你的输入>
```
