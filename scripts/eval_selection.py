# -*- coding: utf-8 -*-
"""精选门槛校准评测（纯标准库；对标 AIHOT scripts/eval-selection.ts + SelectBench + docs/selection.md）。

为什么需要它：collector/config.json 里的 tiers.select_threshold（55/65）和评分
prompt 都是"标准"。改了标准不重新校准门槛，精选要么淹要么枯；凭感觉改数字，
下一轮 CI 就悄悄发布一个更差的站点。AIHOT 的做法：拿 100–200 条你自己标注的
样本，跑"预筛之后的两次独立评分"，看查准/查全/覆盖率与门槛扫描，先改标准、
再动门槛，并支持两版评测报告并排对比（SelectBench）。本脚本把同一套纪律带到 PAT-HOT。

样本文件 .data/gold.jsonl（.data/ 不进 Git），每行一条：
  {"case_id":"laser-001","channel":"tech","title":"…","summary":"…（可为空）",
   "source":"OFweek 激光频道","tier":"media","published_at":"2026-10-01",
   "url":"https://…","gold":"select|reject|either"}
gold 按"这条资料本身该不该进精选"标，不要因为同事件已选过另一篇就标 reject。

跑法（需要 SENSENOVA_API_KEY，真实调用模型；失败绝不伪造结果）：
  $env:SENSENOVA_API_KEY="…"; python scripts/eval_selection.py
  python scripts/eval_selection.py --gold .data/gold.jsonl --label 第二版评分标准 --compare .data/eval/prev.json
  python scripts/eval_selection.py --self-test   # 离线自检指标、分层门槛扫描与并排对比逻辑

输出：
  终端打印指标摘要（若提供 --compare 则额外输出与基线报告的 SelectBench 并排差值与升降级错例）；
  完整错例与逐条结果写到 .data/eval/<时间戳>-<label>.json。
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
try:
    import collect  # noqa: E402
except ImportError:
    collect = None

THRESHOLD_SWEEP = range(40, 91, 5)
VALID_CHANNELS = ("physics", "astro", "tech")


def _digest(item, prompt_key, channel="tech"):
    """评分请求内容指纹：频道 + 条目材料 + prompt_key。任何一侧变了都算新请求。"""
    h = hashlib.sha1()
    h.update(("%s|%s|" % (channel or "tech", prompt_key)).encode("utf-8"))
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


def _render_channel_prompt(key, cfg, channel="tech"):
    """按样本所属频道渲染评分 prompt，确保 physics/astro/tech 各自使用本领域口径。"""
    if collect is None:
        return (cfg.get("prompts") or {}).get(key, "")
    prev_ch = getattr(collect, "_CH", "tech")
    try:
        if channel in VALID_CHANNELS:
            collect._CH = channel
        return collect._ch_prompt(key, cfg)
    finally:
        collect._CH = prev_ch


def score_case(item, cache, cfg, miss_counter, channel="tech"):
    """跑两次独立评分，返回 (a, b)；任一失败返回 (None, None) 并计入覆盖率损失。"""
    scores = []
    ch = channel if channel in VALID_CHANNELS else "tech"
    for key in ("score_a", "score_b"):
        # 缓存键含按样本所属频道"渲染后"的 prompt 哈希：_ch_prompt 会按频道替换领域词，
        # 绑定样本频道可避免 physics/astro 样本误用 tech 频道的 prompt 或缓存。
        rendered = _render_channel_prompt(key, cfg, ch)
        ck = "%s|%s" % (_digest(item, key, ch),
                        hashlib.sha1(rendered.encode("utf-8")).hexdigest()[:12])
        if ck in cache:
            scores.append(cache[ck])
            continue
        prev_ch = getattr(collect, "_CH", "tech")
        try:
            collect._CH = ch
            got = collect._llm_score_once([item], key, cfg)
        except Exception as e:
            print("  [!] %s 评分失败：%s" % (item.get("case_id"), str(e)[:120]))
            return None, None
        finally:
            collect._CH = prev_ch
        if 0 not in got:
            return None, None
        cache[ck] = got[0]
        miss_counter[0] += 1
        scores.append(got[0])
        time.sleep(0.8)
    return scores[0], scores[1]


def metrics(cases, thresholds, sweep_lo=40, sweep_hi=90, sweep_step=5):
    """cases: [{avg|None, tier, gold, channel?}]. 指标口径照搬 AIHOT docs/selection.md：
    - 质量指标分母只含"成功得到决定"且 gold≠either 的样本（有效输出准确率）；
    - 覆盖率 = 成功得到决定 / 全部非 either；
    - 完整准确率把模型失败也算作没做对——失败样本不许从分母里消失；
    - 门槛扫描同时报统一门槛与保持 official/media 级差的分层门槛扫描。"""
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

    all_tiers = set(c["tier"] for c in done) | {"media", "official"}
    sweep = []
    for t in range(sweep_lo, sweep_hi + 1, sweep_step):
        p2, r2, f2, a2, *_ = _prf({k: t for k in all_tiers})
        sweep.append({"threshold": t, "precision": p2, "recall": r2, "f1": f2, "accuracy": a2})
    best = max((s for s in sweep if s["f1"] is not None), key=lambda s: s["f1"], default=None)

    # 分层保持级差扫描：以 media 门槛为基准，official 等其他 tier 保持与 media 的既定差值（如 -10）
    base_media = thresholds.get("media", 65)
    tier_offsets = {k: thresholds.get(k, base_media) - base_media for k in all_tiers}
    tier_sweep = []
    for media_t in range(sweep_lo, sweep_hi + 1, sweep_step):
        shifted = {k: media_t + off for k, off in tier_offsets.items()}
        p3, r3, f3, a3, *_ = _prf(shifted)
        tier_sweep.append({
            "media_threshold": media_t,
            "official_threshold": shifted.get("official", media_t - 10),
            "precision": p3,
            "recall": r3,
            "f1": f3,
            "accuracy": a3,
        })
    best_tiered = max((s for s in tier_sweep if s["f1"] is not None), key=lambda s: s["f1"], default=None)

    return {
        "n_cases": len(cases), "n_non_either": len(non_ei), "n_scored": len(done),
        "precision": prec, "recall": rec, "f1": f1,
        "valid_accuracy": acc, "coverage": coverage, "complete_accuracy": complete,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "threshold_sweep": sweep, "best_uniform_threshold": best,
        "tier_offset_sweep": tier_sweep, "best_tier_thresholds": best_tiered,
    }


def compare_reports(curr, prev):
    """对标 AIHOT SelectBench：将当前评测结果与上一版基线报告并排对比。
    返回核心指标差值（delta）以及从错变对（fixed）、从对变错（regressed）的样本清单。
    """
    cm = (curr or {}).get("metrics") or {}
    pm = (prev or {}).get("metrics") or {}
    keys = ("precision", "recall", "f1", "valid_accuracy", "coverage", "complete_accuracy")
    deltas = {}
    for k in keys:
        cv, pv = cm.get(k), pm.get(k)
        deltas[k] = round(cv - pv, 4) if (isinstance(cv, (int, float)) and isinstance(pv, (int, float))) else None

    prev_by_id = {r.get("case_id"): r for r in ((prev or {}).get("results") or []) if r.get("case_id")}
    fixed = []
    regressed = []
    score_shifts = []

    for r in ((curr or {}).get("results") or []):
        cid = r.get("case_id")
        gold = r.get("gold")
        if not cid or gold not in ("select", "reject") or cid not in prev_by_id:
            continue
        pr = prev_by_id[cid]
        want = (gold == "select")
        c_ok = (r.get("pred_select") == want) if r.get("pred_select") is not None else False
        p_ok = (pr.get("pred_select") == want) if pr.get("pred_select") is not None else False
        if c_ok and not p_ok:
            fixed.append({"case_id": cid, "gold": gold, "prev_avg": pr.get("avg"), "curr_avg": r.get("avg"), "title": r.get("title", "")})
        elif p_ok and not c_ok:
            regressed.append({"case_id": cid, "gold": gold, "prev_avg": pr.get("avg"), "curr_avg": r.get("avg"), "title": r.get("title", "")})
        if isinstance(r.get("avg"), (int, float)) and isinstance(pr.get("avg"), (int, float)):
            diff = round(r["avg"] - pr["avg"], 1)
            if abs(diff) >= 10.0:
                score_shifts.append({"case_id": cid, "delta_avg": diff, "prev_avg": pr["avg"], "curr_avg": r["avg"], "title": r.get("title", "")})

    return {
        "prev_label": (prev or {}).get("label", "baseline"),
        "curr_label": (curr or {}).get("label", "current"),
        "deltas": deltas,
        "fixed": fixed,
        "regressed": regressed,
        "large_score_shifts": score_shifts,
    }


def self_test():
    """离线自检：验证 metrics()、覆盖率惩罚、分层门槛扫描、频道隔离指纹与 SelectBench 并排对比。"""
    thresholds = {"official": 55, "media": 65}
    sample_cases = [
        {"case_id": "c1", "tier": "official", "gold": "select", "avg": 60.0},  # TP (60 >= 55)
        {"case_id": "c2", "tier": "media", "gold": "select", "avg": 70.0},     # TP (70 >= 65)
        {"case_id": "c3", "tier": "media", "gold": "reject", "avg": 60.0},     # TN (60 < 65)
        {"case_id": "c4", "tier": "media", "gold": "reject", "avg": 68.0},     # FP (68 >= 65)
        {"case_id": "c5", "tier": "official", "gold": "select", "avg": None},  # 模型失败：扣减 coverage 与 complete_accuracy
        {"case_id": "c6", "tier": "media", "gold": "either", "avg": 50.0},     # either 不进分母
    ]
    m = metrics(sample_cases, thresholds)
    assert m["n_cases"] == 6 and m["n_non_either"] == 5 and m["n_scored"] == 4
    assert m["tp"] == 2 and m["tn"] == 1 and m["fp"] == 1 and m["fn"] == 0
    assert abs(m["coverage"] - 0.8) < 1e-6, "覆盖率应为 4/5 = 0.8"
    assert abs(m["valid_accuracy"] - 0.75) < 1e-6, "有效输出准确率应为 3/4 = 0.75"
    assert abs(m["complete_accuracy"] - 0.6) < 1e-6, "完整准确率应把失败样本留在分母：3/5 = 0.6"
    assert m["best_tier_thresholds"] is not None, "分层级差门槛扫描应产出最优项"

    # 频道隔离指纹：同一条目在 physics 与 tech 频道必须生成不同缓存摘要
    it = {"title": "超导量子比特退相干抑制", "summary": "实验结果", "published_at": "2026-10-12", "url": "https://e/1"}
    assert _digest(it, "score_a", "physics") != _digest(it, "score_a", "tech"), "不同频道的评分缓存键必须严格隔离"

    # SelectBench 并排对比：验证 fixed 与 regressed 识别准确
    prev_rep = {
        "label": "v1",
        "metrics": m,
        "results": [
            {"case_id": "c1", "gold": "select", "avg": 50.0, "pred_select": False, "title": "T1"},
            {"case_id": "c2", "gold": "reject", "avg": 50.0, "pred_select": False, "title": "T2"},
        ],
    }
    curr_rep = {
        "label": "v2",
        "metrics": dict(m, f1=0.90, complete_accuracy=0.80),
        "results": [
            {"case_id": "c1", "gold": "select", "avg": 65.0, "pred_select": True, "title": "T1"},   # fixed!
            {"case_id": "c2", "gold": "reject", "avg": 70.0, "pred_select": True, "title": "T2"},   # regressed!
        ],
    }
    cmp_out = compare_reports(curr_rep, prev_rep)
    assert [x["case_id"] for x in cmp_out["fixed"]] == ["c1"], "应识别出 c1 从错变对"
    assert [x["case_id"] for x in cmp_out["regressed"]] == ["c2"], "应识别出 c2 从对变错"
    assert abs(cmp_out["deltas"]["complete_accuracy"] - 0.2) < 1e-6
    print("self-test: OK")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gold", default=os.path.join(ROOT, ".data", "gold.jsonl"))
    ap.add_argument("--label", default="未命名标准")
    ap.add_argument("--channel", default="tech", choices=VALID_CHANNELS,
                    help="样本未指定 channel 字段时的默认频道（默认 tech）")
    ap.add_argument("--compare", default="", help="上一版评测报告 JSON 路径，用于并排对比（SelectBench）")
    ap.add_argument("--limit", type=int, default=0, help="最多抽多少条（默认全跑）")
    ap.add_argument("--cache", default=os.path.join(ROOT, ".data", "eval-cache.json"))
    ap.add_argument("--out-dir", default=os.path.join(ROOT, ".data", "eval"))
    ap.add_argument("--self-test", action="store_true", help="离线自检评测指标与并排对比逻辑")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

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
        ch = c.get("channel") or args.channel
        item = {"title": c.get("title", ""), "summary": c.get("summary"),
                "published_at": c.get("published_at"), "url": c.get("url", ""),
                "source": c.get("source", ""), "source_base": c.get("source", "")}
        a, b = score_case(item, cache, cfg, misses, channel=ch)
        avg = round((a + b) / 2, 1) if (a is not None and b is not None) else None
        th = thresholds.get(c.get("tier") or "media", thresholds["media"])
        pred = None if avg is None else (avg >= th)
        results.append({"case_id": c.get("case_id"), "channel": ch,
                        "tier": c.get("tier") or "media",
                        "gold": c.get("gold", "either"), "score_a": a, "score_b": b,
                        "avg": avg, "threshold": th, "pred_select": pred,
                        "title": item["title"]})
        print("  [%d/%d] %-14s [%s] avg=%-6s gold=%-7s pred=%s"
              % (i + 1, len(cases), str(c.get("case_id"))[:14], ch,
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
    if m["best_tier_thresholds"]:
        bt = m["best_tier_thresholds"]
        print("分层级差扫描最优：official≥%s / media≥%s -> F1=%s"
              % (bt["official_threshold"], bt["media_threshold"], fmt(bt["f1"])))
    if m["best_uniform_threshold"]:
        b = m["best_uniform_threshold"]
        print("统一门槛扫描最优：threshold=%s f1=%s（仅供参考；决策按 tier）"
              % (b["threshold"], fmt(b["f1"])))
    print("\n扫描（保持 official/media 级差）：")
    for s in m["tier_offset_sweep"]:
        print("  official≥%d/media≥%d  P=%s R=%s F1=%s"
              % (s["official_threshold"], s["media_threshold"],
                 fmt(s["precision"]), fmt(s["recall"]), fmt(s["f1"])))
    print("\n判错 %d 条：" % len(wrong))
    for w in wrong[:20]:
        print("  %-14s %-7s avg=%-6s（门槛 %s）%s"
              % (w["case_id"], w["gold"], w["avg"], w["threshold"], w["title"][:36]))

    report_payload = {
        "label": args.label,
        "metrics": m,
        "results": results,
        "wrong": wrong,
        "thresholds": thresholds,
    }

    if args.compare and os.path.exists(args.compare):
        with io.open(args.compare, encoding="utf-8") as pf:
            prev_rep = json.load(pf)
        cmp_out = compare_reports(report_payload, prev_rep)
        report_payload["comparison"] = cmp_out
        print("\n===== SelectBench 并排对比 (%s -> %s) ====="
              % (cmp_out["prev_label"], cmp_out["curr_label"]))
        d = cmp_out["deltas"]
        sfmt = lambda x: ("%+.3f" % x) if x is not None else "n/a"
        print("Δ查准 %s · Δ查全 %s · ΔF1 %s · Δ覆盖率 %s · Δ完整准确率 %s"
              % (sfmt(d["precision"]), sfmt(d["recall"]), sfmt(d["f1"]),
                 sfmt(d["coverage"]), sfmt(d["complete_accuracy"])))
        print("由错变对 (Fixed): %d 条 · 由对变错 (Regressed): %d 条"
              % (len(cmp_out["fixed"]), len(cmp_out["regressed"])))
        for fx in cmp_out["fixed"][:10]:
            print("  [+] %-14s gold=%-7s %s -> %s  %s"
                  % (fx["case_id"], fx["gold"], fx["prev_avg"], fx["curr_avg"], fx["title"][:32]))
        for rg in cmp_out["regressed"][:10]:
            print("  [-] %-14s gold=%-7s %s -> %s  %s"
                  % (rg["case_id"], rg["gold"], rg["prev_avg"], rg["curr_avg"], rg["title"][:32]))

    os.makedirs(args.out_dir, exist_ok=True)
    out = os.path.join(args.out_dir, "%s-%s.json" % (time.strftime("%Y%m%d-%H%M%S"),
                                                     args.label.replace(" ", "_")))
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, ensure_ascii=False, indent=1)
    print("\n[*] 完整报告：%s（新增模型请求 %d 次，其余走缓存不重复花钱）"
          % (out, misses[0]))
    print("[*] 提醒：先看错例改评分标准（selection 该写进\"必须正常评价\"、"
          "噪声该写进\"必须压住\"），标准改完再动门槛——门槛只能整体平移，"
          "解决不了\"哪一类判错了\"。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
