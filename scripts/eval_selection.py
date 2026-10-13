# -*- coding: utf-8 -*-
"""精选门槛校准评测（纯标准库；对标 AIHOT scripts/eval-selection.ts + docs/selection.md）。

为什么需要它：collector/config.json 里的 tiers.select_threshold（55/65）和评分
prompt 都是"标准"。改了标准不重新校准门槛，精选要么淹要么枯；凭感觉改数字，
下一轮 CI 就悄悄发布一个更差の站点。AIHOT 的做法：拿 100–200 条你自己标注的
样本，跑"预筛之后的两次独立评分"，看查准/查全/覆盖率与门槛扫描，先改标准、
再动门槛。本脚本把同一套纪律带到 PAT-HOT。

样本文件 .data/gold.jsonl（.data/ 不进 Git），每行一条：
  {"case_id":"laser-001","title":"…","summary":"…（可为空）",
   "source":"OFweek 激光频道","tier":"media","published_at":"2026-10-01",
   "url":"https://…","gold":"select|reject|either"}
gold 按"这条资料本身该不该进精选"标，不要因为同事件已选过另一篇就标 reject。

跑法（需要 SENSENOVA_API_KEY，真实调用模型；失败绝不伪造结果）：
  $env:SENSENOVA_API_KEY="…"; python scripts/eval_selection.py
  python scripts/eval_selection.py --gold .data/gold.jsonl --label 第一版评分标准

输出：
  终端打印指标摘要；完整错例与逐条结果写到 .data/eval/<时间戳>-<label>.json。
  结果按请求内容缓存到 .data/eval-cache.json——同一条材料重跑不重复花钱
  （AIHOT 回执语义的静态版：先付过的钱复用，不二次消费）。
"""
import argparse
import hashlib
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "collector"))
import collect  # noqa: E402

THRESHOLD_SWEEP = range(40, 91, 5)


def _digest(item, prompt_key):
    """评分请求内容指纹：条目材料 + 所用 prompt 文本。任何一侧变了都算新请求。"""
    h = hashlib.sha1()
    h.update(prompt_key.encode("utf-8"))
    h.update(("\x1f".join([str(item.get("title", "")), str(item.get("summary", "")),
                            str(item.get("published_at", "")), str(item.get("url", ""))
                            ])).encode("utf-8"))
    return h.hexdigest()[:16]


def load_cache(path):
    if os.path.exists(path):
        try:
            with io.open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(path, cache):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def score_case(item, cache, cfg, miss_counter):
    """跑两次独立评分，返回 (a, b)；任一失败返回 (None, None) 并计入覆盖率损失。"""
    scores = []
    for key in ("score_a", "score_b"):
        ck = "%s|%s" % (_digest(item, key),
                        hashlib.sha1(cfg["prompts"][key].encode("utf-8")).hexdigest()[:12])
        if ck in cache:
            scores.append(cache[ck])
            continue
        try:
            got = collect._llm_score_once([item], key, cfg)
        except Exception as e:
            print("  [!] %s 评分失败：%s" % (item.get("case_id"), str(e)[:120]))
            return None, None
        if 0 not in got:
            return None, None
        cache[ck] = got[0]
        miss_counter[0] += 1
        scores.append(got[0])
        time.sleep(0.8)
    return scores[0], scores[1]


def metrics(cases, thresholds, sweep_lo=40, sweep_hi=90, sweep_step=5):
    """cases: [{avg|None, tier, gold}]。指标口径照搬 AIHOT docs/selection.md：
    - 质量指标分母只含"成功得到决定"且 gold≠either 的样本（有效输出准确率）；
    - 覆盖率 = 成功得到决定 / 全部非 either；
    - 完整准确率把模型失败也算作没做对——失败样本不许从分母里消失；
    - 门槛扫描同时报三套数，防止"用高失败率换高表面准确率"。"""
    non_ei = [c for c in cases if c["gold"] != "either"]
    done = [c for c in non_ei if c["avg"] is not None]

    def _prf(th_by_tier):
        tp = fp = fn = tn = 0
        for c in done:
            pred = c["avg"] >= th_by_tier.get(c["tier"], th_by_tier.get("media", 65))
            if pred and c["gold"] == "select":
                tp += 1
            elif pred and c["gold"] == "reject":
                fp += 1
            elif (not pred) and c["gold"] == "select":
                fn += 1
            else:
                tn += 1
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else (0.0 if (prec is not None and rec is not None) else None)
        acc = (tp + tn) / len(done) if done else None
        return prec, rec, f1, acc, tp, fp, fn, tn

    prec, rec, f1, acc, tp, fp, fn, tn = _prf(thresholds)
    coverage = len(done) / len(non_ei) if non_ei else None
    complete = (tp + tn) / len(non_ei) if non_ei else None
    sweep = []
    for t in range(sweep_lo, sweep_hi + 1, sweep_step):
        p2, r2, f2, a2, *_ = _prf({k: t for k in set(c["tier"] for c in done) | {"media", "official"}})
        # 扫描按"统一门槛"演示敏感性；实际决策按 tier，故同时给出按 tier 偏移 ±0 的口径
        sweep.append({"threshold": t, "precision": p2, "recall": r2, "f1": f2, "accuracy": a2})
    best = max((s for s in sweep if s["f1"] is not None), key=lambda s: s["f1"], default=None)
    return {
        "n_cases": len(cases), "n_non_either": len(non_ei), "n_scored": len(done),
        "precision": prec, "recall": rec, "f1": f1,
        "valid_accuracy": acc, "coverage": coverage, "complete_accuracy": complete,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "threshold_sweep": sweep, "best_uniform_threshold": best,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gold", default=os.path.join(ROOT, ".data", "gold.jsonl"))
    ap.add_argument("--label", default="未命名标准")
    ap.add_argument("--limit", type=int, default=0, help="最多抽多少条（默认全跑）")
    ap.add_argument("--cache", default=os.path.join(ROOT, ".data", "eval-cache.json"))
    ap.add_argument("--out-dir", default=os.path.join(ROOT, ".data", "eval"))
    args = ap.parse_args()

    if not os.path.exists(args.gold):
        print("找不到样本文件：%s\n"
              "先按脚本头部说明准备 100–200 条标注（多放难例），再来跑评测。" % args.gold)
        return 2
    if not os.environ.get("SENSENOVA_API_KEY"):
        print("未设置 SENSENOVA_API_KEY：评测必须真调模型，绝不伪造结果。")
        return 2

    with io.open(args.gold, encoding="utf-8") as f:
        cases = [json.loads(l) for l in f if l.strip()]
    if args.limit:
        cases = cases[:args.limit]
    cfg = collect.CONFIG
    thresholds = {k: v["select_threshold"] for k, v in cfg["tiers"].items()
                  if isinstance(v, dict) and "select_threshold" in v}
    cache = load_cache(args.cache)
    misses = [0]
    results = []
    print("[*] 评测 %d 条（门槛 official≥%s / media≥%s，标准标签：%s）"
          % (len(cases), thresholds.get("official"), thresholds.get("media"), args.label))
    for i, c in enumerate(cases):
        item = {"title": c.get("title", ""), "summary": c.get("summary"),
                "published_at": c.get("published_at"), "url": c.get("url", ""),
                "source": c.get("source", ""), "source_base": c.get("source", "")}
        a, b = score_case(item, cache, cfg, misses)
        avg = round((a + b) / 2, 1) if (a is not None and b is not None) else None
        th = thresholds.get(c.get("tier") or "media", thresholds["media"])
        pred = None if avg is None else (avg >= th)
        results.append({"case_id": c.get("case_id"), "tier": c.get("tier") or "media",
                        "gold": c.get("gold", "either"), "score_a": a, "score_b": b,
                        "avg": avg, "threshold": th, "pred_select": pred,
                        "title": item["title"]})
        print("  [%d/%d] %-14s avg=%-6s gold=%-7s pred=%s"
              % (i + 1, len(cases), str(c.get("case_id"))[:14],
                 avg, c.get("gold"), pred))
    save_cache(args.cache, cache)

    m = metrics(results, thresholds)
    wrong = [r for r in results
             if r["gold"] in ("select", "reject") and r["pred_select"] is not None
             and r["pred_select"] != (r["gold"] == "select")]
    print("\n===== 指标 =====")
    fmt = lambda x: ("%.3f" % x) if x is not None else "n/a"
    print("样本 %d（非 either %d，成功评分 %d）" % (m["n_cases"], m["n_non_either"], m["n_scored"]))
    print("有效输出：查准 %s · 查全 %s · F1 %s · 准确率 %s（TP %d FP %d FN %d TN %d）"
          % (fmt(m["precision"]), fmt(m["recall"]), fmt(m["f1"]),
             fmt(m["valid_accuracy"]), m["tp"], m["fp"], m["fn"], m["tn"]))
    print("覆盖率 %s · 完整准确率 %s（模型失败也算没做对，不从分母消失）"
          % (fmt(m["coverage"]), fmt(m["complete_accuracy"])))
    if m["best_uniform_threshold"]:
        b = m["best_uniform_threshold"]
        print("统一门槛扫描最优：threshold=%s f1=%s（仅供参考；决策按 tier）"
              % (b["threshold"], fmt(b["f1"])))
    print("\n扫描（统一门槛近似）：")
    for s in m["threshold_sweep"]:
        print("  t=%d  P=%s R=%s F1=%s" % (s["threshold"], fmt(s["precision"]),
                                             fmt(s["recall"]), fmt(s["f1"])))
    print("\n判错 %d 条：" % len(wrong))
    for w in wrong[:20]:
        print("  %-14s %-7s avg=%-6s（门槛 %s）%s"
              % (w["case_id"], w["gold"], w["avg"], w["threshold"], w["title"][:36]))

    os.makedirs(args.out_dir, exist_ok=True)
    out = os.path.join(args.out_dir, "%s-%s.json" % (time.strftime("%Y%m%d-%H%M%S"),
                                                     args.label.replace(" ", "_")))
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump({"label": args.label, "metrics": m, "results": results,
                   "wrong": wrong, "thresholds": thresholds}, f,
                  ensure_ascii=False, indent=1)
    print("\n[*] 完整报告：%s（新增模型请求 %d 次，其余走缓存不重复花钱）"
          % (out, misses[0]))
    print("[*] 提醒：先看错例改评分标准（selection 该写进\"必须正常评价\"、"
          "噪声该写进\"必须压住\"），标准改完再动门槛——门槛只能整体平移，"
          "解决不了\"哪一类判错了\"。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
