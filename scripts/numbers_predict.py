#!/usr/bin/env python3
"""ナンバーズ 予想組み立て

各位独立（重複可・順序あり）なので、ロト6の貪欲＋制約ループは
「各位ごとに重み付きスコア上位を選ぶ」に単純化される。
モードは重み調整＋echo削減で分岐させ、合計値ターゲットのみ2段組み立て。
"""

import math
import random
import statistics
from collections import Counter

from numbers_common import (
    BASE_WEIGHTS, MODE_WEIGHTS, MODE_NAMES, MODE_SIGNATURE,
    ECHO_FACTORS, ECHO_REDUCTION, normalize, _seed_from_str,
)

PULL_GRADIENT = [0.40, 0.25, 0.15, 0.12, 0.08]
SUM_TARGET_TOPK = 4


# ---- 因子行列 ----

def compute_factors(freq_data, cycle_data, rf_scores, lstm_scores, draws, D):
    """各位×0-9の正規化済み因子行列を作る（モード間で共有）。"""
    per_pos = freq_data["per_position"]
    cyc = cycle_data["per_position"]
    rf = rf_scores["per_position"]
    lstm = lstm_scores["per_position"]

    factors = {}
    for p in range(D):
        ps = per_pos[str(p)]
        freq_raw = {d: ps["percentages"][str(d)] for d in range(10)}
        recent_raw = {d: 0.6 * ps["recent_100"][str(d)] + 0.4 * ps["recent_300"][str(d)] for d in range(10)}
        drought_raw = {d: ps["drought"][str(d)] / max(1e-6, ps["avg_intervals"][str(d)]) for d in range(10)}
        cycle_raw = {d: cyc[str(p)][str(d)]["cycle_score"] for d in range(10)}
        rf_raw = {d: rf[str(p)][str(d)] for d in range(10)}
        lstm_raw = {d: lstm[str(p)][str(d)] for d in range(10)}

        pull_raw = {d: 0.0 for d in range(10)}
        for k, w in enumerate(PULL_GRADIENT):
            idx = len(draws) - 1 - k
            if idx >= 0:
                pull_raw[draws[idx]["digits"][p]] += w

        factors[p] = {
            "freq": normalize(freq_raw),
            "recent": normalize(recent_raw),
            "drought": normalize(drought_raw),
            "cycle": normalize(cycle_raw),
            "rf": normalize(rf_raw),
            "lstm": normalize(lstm_raw),
            "pull": normalize(pull_raw),
        }

    sums = [sum(dr["digits"]) for dr in draws]
    avg_sum = statistics.mean(sums) if sums else 0.0
    std_sum = statistics.pstdev(sums) if len(sums) > 1 else 0.0
    return {
        "factors": factors,
        "avg_sum": avg_sum,
        "std_sum": std_sum,
        "sum_range": (avg_sum - std_sum, avg_sum + std_sum),
        "last_digits": draws[-1]["digits"] if draws else [],
    }


def effective_weights(mode_key):
    """モードの重み: BASE×MODE倍率、非署名のecho因子は削減。"""
    w = {f: BASE_WEIGHTS[f] * MODE_WEIGHTS.get(mode_key, {}).get(f, 1.0) for f in BASE_WEIGHTS}
    sig = MODE_SIGNATURE.get(mode_key, set())
    for f in ECHO_FACTORS:
        if f not in sig:
            w[f] *= (1 - ECHO_REDUCTION)
    return w


def weighted_base(factors, weights, D):
    """因子行列×重み → base_scores[p][d]。"""
    base = {}
    for p in range(D):
        base[p] = {d: sum(weights.get(f, 0.0) * factors[p][f][d] for f in factors[p]) for d in range(10)}
    return base


# ---- モンテカルロ / ランダム基準 ----

def monte_carlo_confidence(base_scores, D, has_mini, recommended, n_trials=10000, seed_str="mc"):
    """各位を base_scores に比例して独立抽選し、各位%と推奨番号のstraight/box/mini%を返す。"""
    if n_trials <= 0:
        # バックテスト等で信頼度が不要な場合はスキップ（予想数字のみ使う）
        return {"per_position": {}, "straight_pct": 0.0, "box_pct": 0.0,
                "mini_pct": 0.0 if has_mini else None}
    rng = random.Random(_seed_from_str(seed_str))
    wpos = {}
    for p in range(D):
        w = [max(0.0, base_scores[p][d]) for d in range(10)]
        s = sum(w) or 1.0
        wpos[p] = [x / s for x in w]

    counts = {p: [0] * 10 for p in range(D)}
    straight = box = mini = 0
    rec_sorted = sorted(recommended)
    rec_mini = recommended[-2:] if has_mini else None
    for _ in range(n_trials):
        pick = []
        for p in range(D):
            r = rng.random()
            acc = 0.0
            chosen = 9
            for d in range(10):
                acc += wpos[p][d]
                if r <= acc:
                    chosen = d
                    break
            pick.append(chosen)
            counts[p][chosen] += 1
        if pick == recommended:
            straight += 1
        if sorted(pick) == rec_sorted:
            box += 1
        if has_mini and pick[-2:] == rec_mini:
            mini += 1

    return {
        "per_position": {str(p): {str(d): round(counts[p][d] / n_trials * 100, 2) for d in range(10)} for p in range(D)},
        "straight_pct": round(straight / n_trials * 100, 3),
        "box_pct": round(box / n_trials * 100, 3),
        "mini_pct": round(mini / n_trials * 100, 3) if has_mini else None,
    }


def simulate_random_baseline(total_rounds, D, has_mini):
    """ナンバーズの理論確率（解析解）。ロト6の超幾何を置換。"""
    straight_prob = 1 / (10 ** D)
    mini_prob = 1 / 100 if has_mini else None
    # k桁一致の分布: C(D,k)(1/10)^k(9/10)^(D-k)
    match_dist = {}
    for k in range(D + 1):
        p = math.comb(D, k) * (0.1 ** k) * (0.9 ** (D - k))
        match_dist[str(k)] = round(p, 6)
    return {
        "total_rounds": total_rounds,
        "straight_prob": straight_prob,
        "expected_straight_hits": round(straight_prob * total_rounds, 4),
        "mini_prob": mini_prob,
        "expected_mini_hits": round(mini_prob * total_rounds, 3) if has_mini else None,
        "position_match_distribution": match_dist,
    }


# ---- 選出根拠 ----

def _factor_phrase(factor, p, d, freq_data, cycle_data, rf_scores, lstm_scores, draws, D, positions):
    label = positions[p]
    ps = freq_data["per_position"][str(p)]
    n = freq_data["per_position"][str(p)]["counts"]  # for total we use sum
    total = sum(int(v) for v in ps["counts"].values())
    if factor == "freq":
        c = ps["counts"][str(d)]
        pct = ps["percentages"][str(d)]
        return f"{label}で全{total}回中{c}回 {d} が出現（{pct}%）"
    if factor == "recent":
        return f"{label}で直近100回 {ps['recent_100'][str(d)]}% と好調"
    if factor == "drought":
        dr = ps["drought"][str(d)]
        ai = ps["avg_intervals"][str(d)]
        ratio = round(dr / ai, 1) if ai else 0
        return f"{label}で平均{ai}回間隔に対し{dr}回未出（{ratio}倍・そろそろ）"
    if factor == "pull":
        return f"前回 {label} も {d}（引っ張り）"
    if factor == "cycle":
        cyc = cycle_data["per_position"][str(p)][str(d)]
        c = cyc.get("dominant_cycle")
        return f"{label}で約{c}回周期の出現タイミング" if c else f"{label}の周期指標"
    if factor == "rf":
        pr = round(rf_scores["per_position"][str(p)][str(d)] * 100, 1)
        return f"RFが {label} で {d} を確率{pr}%と予測"
    if factor == "lstm":
        pr = round(lstm_scores["per_position"][str(p)][str(d)] * 100, 1)
        return f"LSTMが {label} で {d} を確率{pr}%と予測"
    return f"{label}で {d} を選出"


def _shape_label(digits):
    if len(set(digits)) == 1:
        return "ゾロ目"
    if len(set(digits)) < len(digits):
        return "ダブル(重複あり)"
    asc = all(digits[i + 1] - digits[i] == 1 for i in range(len(digits) - 1))
    desc = all(digits[i] - digits[i + 1] == 1 for i in range(len(digits) - 1))
    if asc or desc:
        return "連番"
    return "バラ"


def _metrics(digits, D):
    odd = sum(1 for x in digits if x % 2 == 1)
    big = sum(1 for x in digits if x >= 5)
    return {
        "sum": sum(digits),
        "odd_even": f"{odd}:{D - odd}",
        "big_small": f"{big}:{D - big}",
        "shape": _shape_label(digits),
    }


def _build_position_entries(digits, base, factors, weights, freq_data, cycle_data,
                            rf_scores, lstm_scores, draws, D, positions):
    entries = []
    for p in range(D):
        chosen = digits[p]
        tot = sum(max(0.0, base[p][d]) for d in range(10)) or 1.0
        # top-3 候補
        ranked = sorted(range(10), key=lambda d: base[p][d], reverse=True)
        candidates = [{
            "digit": d,
            "score": round(base[p][d], 4),
            "confidence": round(max(0.0, base[p][d]) / tot * 100, 2),
        } for d in ranked[:3]]
        # 最も効いた因子
        contrib = {f: weights.get(f, 0.0) * factors[p][f][chosen] for f in factors[p]}
        top_factor = max(contrib, key=contrib.get) if contrib else "freq"
        reason = _factor_phrase(top_factor, p, chosen, freq_data, cycle_data,
                                rf_scores, lstm_scores, draws, D, positions)
        entries.append({
            "position": p,
            "label": positions[p],
            "digit": chosen,
            "confidence": round(max(0.0, base[p][chosen]) / tot * 100, 2),
            "candidates": candidates,
            "top_factor": top_factor,
            "reason_text": reason,
        })
    return entries


# ---- 予想本体 ----

def generate_prediction(base_data, freq_data, cycle_data, rf_scores, lstm_scores,
                        draws, D, game_cfg, mode_key, period_label, date_str, mc_trials=10000):
    factors = base_data["factors"]
    weights = effective_weights(mode_key)
    base = weighted_base(factors, weights, D)

    digits = [max(range(10), key=lambda d: base[p][d]) for p in range(D)]
    positions = game_cfg["positions"]
    has_mini = game_cfg["has_mini"]

    mc = monte_carlo_confidence(
        base, D, has_mini, digits, n_trials=mc_trials,
        seed_str=f"{date_str}_{game_cfg['digits']}_{mode_key}_{period_label}_mc",
    )
    entries = _build_position_entries(digits, base, factors, weights, freq_data,
                                      cycle_data, rf_scores, lstm_scores, draws, D, positions)
    metrics = _metrics(digits, D)
    metrics["target_sum"] = None

    overall = mc["straight_pct"] if mc["straight_pct"] > 0 else round(
        _geo_mean([e["confidence"] / 100 for e in entries]) * 100, 2)

    return {
        "mode_key": mode_key,
        "mode_name": MODE_NAMES[mode_key],
        "digits": digits,
        "number_str": "".join(str(d) for d in digits),
        "per_position": entries,
        "metrics": metrics,
        "monte_carlo": mc,
        "overall_confidence": overall,
    }


def generate_sum_target_prediction(base_data, digit_sum_data, freq_data, cycle_data,
                                   rf_scores, lstm_scores, draws, D, game_cfg,
                                   period_label, date_str, mc_trials=10000):
    """合計値帯を確率的に選び、各位top-K内で合計を寄せる2段予想。"""
    factors = base_data["factors"]
    weights = effective_weights("balanced")
    base = weighted_base(factors, weights, D)
    positions = game_cfg["positions"]
    has_mini = game_cfg["has_mini"]

    # 1) 目標帯を band_weights から決定的に抽選
    bw = digit_sum_data.get("band_weights", {})
    rng = random.Random(_seed_from_str(f"{date_str}_{game_cfg['digits']}_sum_target_{period_label}"))
    target_band = _weighted_pick(bw, rng)
    lo, hi = _band_range(target_band, D)
    center = (lo + hi) / 2

    # 2) 各位top-K候補の直積から、合計が帯内かつ総スコア最大の組合せを選ぶ
    topk = {p: sorted(range(10), key=lambda d: base[p][d], reverse=True)[:SUM_TARGET_TOPK] for p in range(D)}
    best = None
    for combo in _product(topk, D):
        s = sum(combo)
        score = sum(base[p][combo[p]] for p in range(D))
        in_band = lo <= s <= hi
        # 帯内を優先、その中で高スコア、外れなら中心への近さ
        key = (1 if in_band else 0, score if in_band else -abs(s - center))
        if best is None or key > best[0]:
            best = (key, list(combo))
    digits = best[1] if best else [max(range(10), key=lambda d: base[p][d]) for p in range(D)]

    mc = monte_carlo_confidence(
        base, D, has_mini, digits, n_trials=mc_trials,
        seed_str=f"{date_str}_{game_cfg['digits']}_sum_target_{period_label}_mc",
    )
    entries = _build_position_entries(digits, base, factors, weights, freq_data,
                                      cycle_data, rf_scores, lstm_scores, draws, D, positions)
    for e in entries:
        e["reason_text"] = f"目標合計 {target_band} に寄せて {e['label']} で {e['digit']} を選出（候補上位）"
    metrics = _metrics(digits, D)
    metrics["target_sum"] = target_band

    return {
        "mode_key": "sum_target",
        "mode_name": MODE_NAMES["sum_target"],
        "digits": digits,
        "number_str": "".join(str(d) for d in digits),
        "per_position": entries,
        "metrics": metrics,
        "monte_carlo": mc,
        "target_band": {"label": target_band, "range": [lo, hi],
                        "historical_pct": _band_hist_pct(digit_sum_data, target_band)},
        "overall_confidence": mc["straight_pct"],
    }


def run_predictions(base_data, freq_data, cycle_data, rf_scores, lstm_scores,
                    digit_sum_data, draws, D, game_cfg, period_label, date_str):
    preds = {}
    for mode_key in MODE_WEIGHTS:  # balanced, frequency_heavy, ...
        preds[mode_key] = generate_prediction(
            base_data, freq_data, cycle_data, rf_scores, lstm_scores,
            draws, D, game_cfg, mode_key, period_label, date_str)
    preds["sum_target"] = generate_sum_target_prediction(
        base_data, digit_sum_data, freq_data, cycle_data, rf_scores, lstm_scores,
        draws, D, game_cfg, period_label, date_str)
    return preds


# ---- helpers ----

def _geo_mean(vals):
    vals = [v for v in vals if v > 0]
    if not vals:
        return 0.0
    return math.exp(sum(math.log(v) for v in vals) / len(vals))


def _weighted_pick(weights, rng):
    if not weights:
        return "0-2"
    items = sorted(weights.items())  # 決定性のためソート
    total = sum(w for _, w in items) or 1.0
    r = rng.random() * total
    acc = 0.0
    for band, w in items:
        acc += w
        if r <= acc:
            return band
    return items[-1][0]


def _band_range(band, D):
    try:
        lo, hi = band.split("-")
        return int(lo), int(hi)
    except Exception:
        return 0, D * 9


def _band_hist_pct(digit_sum_data, band):
    for b in digit_sum_data.get("bands", []):
        if b["band"] == band:
            return b["percentage"]
    return 0.0


def _product(topk, D):
    """各位の候補リストの直積を生成。"""
    result = [[]]
    for p in range(D):
        result = [prev + [d] for prev in result for d in topk[p]]
    return result
