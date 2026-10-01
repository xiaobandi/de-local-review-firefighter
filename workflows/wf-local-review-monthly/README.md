# 月度口碑报告

> 评分趋势+根因分布+竞店评分对比 → 一页报告

工作流 `wf-local-review-monthly`　·　归属 差评灭火官　·　触发 定时（每月 1 日）　·　
复杂度 S　·　阶段 P1

## 调用链

- `平台评价读取`（platform-review-read）
- `回复话术生成`（reply-copy-generator）

## 文档

- [`WORKFLOW.md`](WORKFLOW.md) — 完整编排、闸门、降级与验收标准
- [`tests/cases.yaml`](tests/cases.yaml) — 端到端 / 闸门 / 降级用例

## 一句话试用

```text
帮我跑 差评灭火官 的「月度口碑报告」：<你的输入>
```
