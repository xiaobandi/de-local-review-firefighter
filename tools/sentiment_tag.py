#!/usr/bin/env python3
"""评论情绪与主题打标（零依赖规则基线）。

把评论流打上「情绪 / 风险 / 主题 / 优先级」四类标签，作为差评预警、
客服分流、选题挖掘三处的共用前置。规则基线负责"不漏"，模型负责"读懂"。

v2 修订（2026-09）
------------------
v1 用「词是否出现在文本里」直接计分，**没有任何否定处理**，导致真实差评
被判为正面（差评预警直接漏报）：
    "质量不好，用了两天就坏了，不推荐买"   → v1 判「正面」
    "不值这个价"                          → v1 判「正面」
    "不推荐，物流太慢了"                   → v1 判「负面」（靠碰巧的「慢」救回）
原因：
  1. 极性词含单字（"好""值""快""香"），"不好""不值"里的正向词照样命中；
  2. 无否定窗口，否定前缀不翻转极性；
  3. 忽略"不推荐/没用/别买"这类否定短语。

v2 起：
  - 逐词匹配后检查**前 2 字内的否定词**（不/没/无/未/别/难/非/勿/拒），命中即翻转极性，
    并加双否定保护（"不得不推荐"不翻转）；
  - 极性词表补入 v1 漏掉的高频负面词（坏/裂/开胶/发霉/寄错/漏发/客服不理…）；
  - "食品安全" 主题的关键词从单字「吃」收紧为「吃出/吃到/变质/过期/异物/发霉/卫生」，
    避免「好吃」被误判为食品安全风险；
  - 每条产出带 `negated` 字段，列出被翻转的词，方便人工复核规则是否误翻。

用法:
    python3 sentiment_tag.py --file reviews.txt
    cat reviews.txt | python3 sentiment_tag.py --json
    python3 sentiment_tag.py --file reviews.txt --csv out.csv
    python3 sentiment_tag.py --selftest

输入：每行一条评论（行内可含 #id:xxx 前缀作标识）。
输出：JSON 或表格，字段见 render()。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# 单一字的极性词必须放在这里，靠 NEGATION 处理否定；多字词优先匹配
# 注意：「态度」「回复」「价格」这类是**主题词**不是极性词，只放进 RISK_TOPICS——
#       v1 把「态度」当负面词，导致「客服态度好」被判成负面（见自测用例）。
NEGATIVE = [
    "差", "垃圾", "骗", "假", "烂", "坑", "失望", "恶心", "无语", "慢", "再也不",
    "别买", "避雷", "翻车", "照骗", "坏", "裂", "开胶", "掉色", "异味", "破损",
    "发霉", "变质", "过期", "寄错", "漏发", "漏气", "不耐用", "划痕", "缩水",
    "退货", "退款", "投诉", "举报", "催", "拖", "糊弄", "敷衍", "拉黑",
    "生气", "恼火", "离谱", "过分", "受害者", "上当",
]
POSITIVE = [
    "喜欢", "满意", "赞", "推荐", "回购", "绝了", "感谢", "惊艳", "惊喜",
    "舒服", "实惠", "划算", "刚好", "完美", "值得", "五星", "秒回",
]
# 单字正向词：只在未被否定、且不与负面词重叠时计正
POSITIVE_SINGLE = ["好", "快", "香", "值", "棒", "美", "稳", "轻"]

NEGATION = ["不", "没", "无", "未", "别", "难", "非", "勿", "拒"]
# 双否定：命中这些片段时不做极性翻转
DOUBLE_NEG_PREFIX = ["不得不", "无不", "不是不", "莫不", "未尝不"]

RISK_TOPICS = {
    "质量": ["质量", "坏", "裂", "掉色", "开胶", "异味", "假", "瑕疵", "划痕"],
    "物流": ["物流", "快递", "发货", "延迟", "慢", "破损", "漏发", "寄错"],
    "服务": ["客服", "态度", "回复", "售后", "不理"],
    "描述不符": ["照骗", "不符", "实物", "不一样", "货不对板"],
    "价格": ["贵", "价格", "涨价", "优惠", "差价"],
    # v1 用单字「吃」，把「好吃」也当成食品安全风险；v2 收紧
    "食品安全": ["吃出", "吃到", "变质", "过期", "异物", "发霉", "卫生", "拉肚子"],
}
VALUE_HINT = ["举报", "投诉", "12315", "差评", "曝光", "平台"]

# 句读边界：否定窗口不得跨过它们
_CLAUSE_SEP = "。！？!?；;，,、\n "


def _has_negation(text: str, start: int) -> bool:
    """词从 start 开始，检查前 2 字内是否有否定词（不跨句读、做双否定保护）。"""
    if start <= 0:
        return False
    for back in (1, 2):
        i = start - back
        if i < 0:
            break
        ch = text[i]
        if ch in _CLAUSE_SEP:
            break
        if ch in NEGATION:
            prefix = text[max(0, i - 3): start + 4]
            if any(d in prefix for d in DOUBLE_NEG_PREFIX):
                return False
            return True
    return False


def _matches(text: str, words: list[str]) -> list[tuple[str, int, bool]]:
    """返回 [(词, 起始位置, 是否被否定)]。"""
    out = []
    for w in words:
        for m in re.finditer(re.escape(w), text):
            out.append((w, m.start(), _has_negation(text, m.start())))
    return out


def tag(line: str) -> dict:
    rid = ""
    text = line
    if line.startswith("#") and ":" in line.split(" ")[0]:
        rid, text = line[1:].split(":", 1)

    pos_hits = _matches(text, POSITIVE)
    neg_hits = _matches(text, NEGATIVE)
    # 单字正向词：被否定的直接算负面单字词，不算正向
    single_hits = _matches(text, POSITIVE_SINGLE)

    pos = sum(1 for _, _, neg in pos_hits + single_hits if not neg)
    neg = sum(1 for _, _, neg in pos_hits + single_hits if neg) \
        + sum(1 for _, _, neg in neg_hits if not neg) \
        + sum(1 for _, _, neg in neg_hits if neg)  # 负面词被否定仍是负面信号，交人工看

    negated = [f"{w}(前有否定)" for w, _, n in pos_hits + single_hits if n]

    if neg and neg >= pos:
        sentiment = "负面"
    elif pos and pos > neg:
        sentiment = "正面"
    else:
        sentiment = "中性"

    topics = [t for t, kws in RISK_TOPICS.items() if any(k in text for k in kws)]
    escalated = sentiment == "负面" and any(v in text for v in VALUE_HINT)

    if escalated:
        level = "P0-立即处理"
    elif sentiment == "负面":
        level = "P1-当日处理"
    elif topics:
        level = "P2-归因分析"
    else:
        level = "P3-常规"

    return {"id": rid or "—", "sentiment": sentiment, "topics": topics or ["未归类"],
            "escalate": escalated, "level": level, "text": text.strip(),
            "negated": negated}


def render(rows: list[dict], csv_mode: bool, out: str | None) -> None:
    if csv_mode:
        f = open(out, "w", encoding="utf-8", newline="") if out else sys.stdout
        w = csv.writer(f)
        w.writerow(["id", "情绪", "主题", "处理等级", "升级", "被翻转的词", "原文"])
        for r in rows:
            w.writerow([r["id"], r["sentiment"], "/".join(r["topics"]), r["level"],
                        "是" if r["escalate"] else "否", "/".join(r["negated"]), r["text"]])
        if out:
            f.close()
            print(f"已写出 {out}（{len(rows)} 条）")
        return
    for r in rows:
        flag = "⚠" if r["escalate"] else " "
        print(f"{flag}[{r['level']}] {r['id']} {r['sentiment']} | {'/'.join(r['topics'])} | {r['text'][:40]}")


def _selftest() -> int:
    """内嵌回归自测：核心断言是「真实差评不得被判为正面」。"""
    checks: list[tuple[str, bool, str]] = []

    def ck(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    # v1 的漏报样本（v1 全部判「正面」）
    for t in ["质量不好，用了两天就坏了，不推荐买",
              "不值这个价，不会再买",
              "不推荐，物流太慢了",
              "不好用，客服也不理"]:
        r = tag(t)
        ck(f"差评判负面：{t[:14]}", r["sentiment"] == "负面", f"实际 {r['sentiment']}")

    # 真差评 + 升级词 → P0
    r = tag("我要投诉你们这是诈骗，马上曝光")
    ck("升级样本判 P0", r["level"].startswith("P0"), f"实际 {r['level']}")
    ck("升级样本 escalate=True", r["escalate"] is True)

    # 真实好评不得被判负面
    for t in ["质量很好，很喜欢，会回购", "物流很快，包装也完好", "客服态度好，回复及时"]:
        r = tag(t)
        ck(f"好评判正面：{t[:14]}", r["sentiment"] == "正面", f"实际 {r['sentiment']}")

    # 双否定不翻转
    ck("双否定「不得不推荐」不算负面",
       tag("不得不推荐，确实好用")["sentiment"] == "正面")

    # 食品安全主题不再被「好吃」误触发
    ck("「好吃」不触发食品安全主题",
       "食品安全" not in tag("好吃，下次还买")["topics"])
    ck("「吃出异物」触发食品安全主题",
       "食品安全" in tag("吃出异物了，太恶心")["topics"])

    # 否定窗口不跨句读
    ck("否定不跨句读", tag("不。这个好用")["sentiment"] == "正面")

    # 中性兜底
    ck("无极性词判中性", tag("一般般吧")["sentiment"] == "中性")

    # 翻转词要留痕，便于人工复核
    ck("翻转词留痕", bool(tag("不好用")["negated"]))

    fails = [(n, d) for n, ok, d in checks if not ok]
    for n, ok, d in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}" + (f" —— {d}" if not ok and d else ""))
    print(f"sentiment_tag 自测：{len(checks) - len(fails)}/{len(checks)} 通过")
    return 1 if fails else 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    ap = argparse.ArgumentParser(description="评论情绪与主题打标")
    ap.add_argument("--file", help="评论文件（每行一条）；缺省 stdin")
    ap.add_argument("--csv", action="store_true")
    ap.add_argument("-o", "--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        print("错误：没有可打标的评论", file=sys.stderr)
        return 2

    rows = [tag(l) for l in lines]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        render(rows, args.csv, args.out)
        neg = sum(1 for r in rows if r["sentiment"] == "负面")
        esc = sum(1 for r in rows if r["escalate"])
        print(f"\n汇总：{len(rows)} 条 | 负面 {neg} | 需升级 {esc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
