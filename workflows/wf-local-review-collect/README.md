# 评价采集与情感分级

> 抓取三平台新增评价 → 情感打分 → 好评/中评/差评分桶

工作流 `wf-local-review-collect`　·　归属 差评灭火官　·　触发 定时（每 2 小时巡检）　·　
复杂度 M（连接器）　·　阶段 P0

## 调用链

- `平台评价读取`（platform-review-read）

## 文档

- [`WORKFLOW.md`](WORKFLOW.md) — 完整编排、闸门、降级与验收标准
- [`tests/cases.yaml`](tests/cases.yaml) — 端到端 / 闸门 / 降级用例

## 一句话试用

```text
帮我跑 差评灭火官 的「评价采集与情感分级」：<你的输入>
```
