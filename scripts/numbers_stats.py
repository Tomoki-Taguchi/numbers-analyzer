#!/usr/bin/env python3
"""ナンバーズ 統計分析

各分析は draws（回号昇順）と桁数 D を受け取り、front-end/予想が消費する
辞書を返す。原子単位は (位置p, 数字d)。0-9 一様に近いゲームのため、各位drought・
引っ張り・周期が頻度より効きやすい点に注意（詳細は tasks/todo.md）。
"""

import statistics
from collections import Counter, defaultdict

from numbers_common import DIGIT_SUM_RECENT_BLEND


def _digits_of(draws):
    return [d["digits"] for d in draws]


def analyze_frequency(draws, D):
    """各位0-9の頻度・drought・平均間隔・hot/cold と、全体頻度。"""
    n = len(draws)
    per_position = {}
    for p in range(D):
        seq = [d["digits"][p] for d in draws]
        counts = Counter(seq)
        counts = {d: counts.get(d, 0) for d in range(10)}
        pct = {d: (counts[d] / n * 100 if n else 0.0) for d in range(10)}

        # drought: 末尾からその数字が最後に出るまでの回数
        drought = {}
        appear_idx = defaultdict(list)
        for i, d in enumerate(seq):
            appear_idx[d].append(i)
        for d in range(10):
            drought[d] = (n - 1 - appear_idx[d][-1]) if appear_idx[d] else n

        # 平均間隔: 連続出現の平均ギャップ（出現<2なら n）
        avg_intervals = {}
        for d in range(10):
            idx = appear_idx[d]
            if len(idx) >= 2:
                gaps = [idx[i + 1] - idx[i] for i in range(len(idx) - 1)]
                avg_intervals[d] = round(sum(gaps) / len(gaps), 2)
            else:
                avg_intervals[d] = float(n)

        recent_100 = _recent_pct(seq, 100)
        recent_300 = _recent_pct(seq, 300)

        ranked = sorted(range(10), key=lambda d: counts[d], reverse=True)
        per_position[str(p)] = {
            "counts": {str(d): counts[d] for d in range(10)},
            "percentages": {str(d): round(pct[d], 2) for d in range(10)},
            "drought": {str(d): drought[d] for d in range(10)},
            "avg_intervals": {str(d): avg_intervals[d] for d in range(10)},
            "recent_100": {str(d): recent_100[d] for d in range(10)},
            "recent_300": {str(d): recent_300[d] for d in range(10)},
            "hot": ranked[:3],
            "cold": ranked[-3:][::-1],
        }

    # 全体（全位合算）
    overall_counts = Counter()
    for d in draws:
        overall_counts.update(d["digits"])
    total_slots = n * D
    overall = {
        "counts": {str(d): overall_counts.get(d, 0) for d in range(10)},
        "percentages": {str(d): round(overall_counts.get(d, 0) / total_slots * 100, 2) if total_slots else 0.0 for d in range(10)},
        "hot": sorted(range(10), key=lambda d: overall_counts.get(d, 0), reverse=True)[:3],
        "cold": sorted(range(10), key=lambda d: overall_counts.get(d, 0))[:3],
    }
    return {"per_position": per_position, "overall": overall}


def _recent_pct(seq, window):
    """直近 window 件での各数字の出現率(%)。"""
    sub = seq[-window:] if len(seq) >= window else seq
    m = len(sub)
    c = Counter(sub)
    return {d: round(c.get(d, 0) / m * 100, 2) if m else 0.0 for d in range(10)}


def analyze_pull(draws, D):
    """引っ張り: 前回と同じ位置で同じ数字が出る傾向。"""
    if len(draws) < 2:
        return {"distribution": {}, "average": 0.0, "per_position_rate": {},
                "last_digits": draws[-1]["digits"] if draws else [], "recent_pulls": []}

    dist = Counter()
    pos_repeat = [0] * D
    transitions = 0
    recent = []
    for i in range(1, len(draws)):
        prev = draws[i - 1]["digits"]
        cur = draws[i]["digits"]
        pulled = [p for p in range(D) if prev[p] == cur[p]]
        dist[len(pulled)] += 1
        for p in pulled:
            pos_repeat[p] += 1
        transitions += 1
        if i >= len(draws) - 10:
            recent.append({
                "round": draws[i]["round"], "date": draws[i]["date"],
                "digits": cur, "pulled_positions": pulled, "pull_count": len(pulled),
            })

    avg = sum(k * v for k, v in dist.items()) / transitions if transitions else 0.0
    return {
        "distribution": {str(k): dist.get(k, 0) for k in range(D + 1)},
        "average": round(avg, 3),
        "per_position_rate": {str(p): round(pos_repeat[p] / transitions, 3) for p in range(D)},
        "last_digits": draws[-1]["digits"],
        "recent_pulls": recent[::-1],
    }


def analyze_cycle(draws, D):
    """(位置,数字)ごとの周期を検出。1パスで出現列を構築。"""
    n = len(draws)
    appear = {p: defaultdict(list) for p in range(D)}
    for i, d in enumerate(draws):
        for p in range(D):
            appear[p][d["digits"][p]].append(i)

    per_position = {}
    for p in range(D):
        pos_res = {}
        for d in range(10):
            idx = appear[p][d]
            if len(idx) < 3:
                pos_res[str(d)] = {"dominant_cycle": None, "cycle_score": 0.0,
                                   "avg_interval": None, "since_last": (n - 1 - idx[-1]) if idx else n,
                                   "next_expected": None, "top_cycles": []}
                continue
            gaps = [idx[i + 1] - idx[i] for i in range(len(idx) - 1)]
            gap_counts = Counter(gaps)
            top_cycles = [{"cycle": c, "count": cnt} for c, cnt in gap_counts.most_common(3)]
            dominant = gap_counts.most_common(1)[0][0]
            avg_gap = sum(gaps) / len(gaps)
            since_last = n - 1 - idx[-1]
            # cycle_score: dominant 周期に対する到来の近さ × 多数決の強さ
            phase = since_last % dominant if dominant else 0
            closeness = max(0.0, min(1.0, 1.0 - min(phase, dominant - phase) / dominant)) if dominant else 0.0
            strength = gap_counts.most_common(1)[0][1] / len(gaps)
            pos_res[str(d)] = {
                "dominant_cycle": dominant,
                "cycle_score": round(closeness * strength, 4),
                "avg_interval": round(avg_gap, 2),
                "since_last": since_last,
                "next_expected": dominant - phase if dominant else None,
                "top_cycles": top_cycles,
            }
        per_position[str(p)] = pos_res
    return {"per_position": per_position}


def analyze_digit_sum(draws, D):
    """合計値の分布・帯・直近ブレンド重み（zone/decade の相当）。"""
    sums = [sum(d["digits"]) for d in draws]
    n = len(sums)
    dist = Counter(sums)
    avg = statistics.mean(sums) if sums else 0.0
    std = statistics.pstdev(sums) if len(sums) > 1 else 0.0

    band_w = 3  # 帯幅
    smax = D * 9

    def band_label(s):
        lo = (s // band_w) * band_w
        return f"{lo}-{min(lo + band_w - 1, smax)}"

    all_bands = Counter(band_label(s) for s in sums)
    recent_window = min(100, n)
    recent_bands = Counter(band_label(s) for s in sums[-recent_window:])

    def top_bands(counter, total):
        return [{"band": b, "count": c, "percentage": round(c / total * 100, 2)}
                for b, c in counter.most_common(10)] if total else []

    # 帯重み: 全期間 + 直近のブレンド
    weights = {}
    for b in set(all_bands) | set(recent_bands):
        aw = all_bands.get(b, 0) / n if n else 0
        rw = recent_bands.get(b, 0) / recent_window if recent_window else 0
        weights[b] = (1 - DIGIT_SUM_RECENT_BLEND) * aw + DIGIT_SUM_RECENT_BLEND * rw

    return {
        "distribution": {str(s): dist.get(s, 0) for s in range(smax + 1)},
        "avg": round(avg, 2),
        "std": round(std, 2),
        "range": [round(avg - std, 1), round(avg + std, 1)],
        "bands": top_bands(all_bands, n),
        "recent_bands": top_bands(recent_bands, recent_window),
        "recent_window": recent_window,
        "band_weights": weights,  # 内部用（analysis 出力時に除去）
    }


def analyze_shape(draws, D):
    """奇偶・大小・ゾロ目・連番・repeat の形パターン（zone の相当）。"""
    n = len(draws)
    if n == 0:
        return {}
    odd_even = Counter()
    big_small = Counter()
    zoro = repeat = seq = 0
    for d in draws:
        dg = d["digits"]
        odd = sum(1 for x in dg if x % 2 == 1)
        big = sum(1 for x in dg if x >= 5)
        odd_even[f"{odd}:{D - odd}"] += 1
        big_small[f"{big}:{D - big}"] += 1
        if len(set(dg)) == 1:
            zoro += 1
        if len(set(dg)) < D:
            repeat += 1
        if _is_sequential(dg):
            seq += 1
    return {
        "odd_even_dist": dict(odd_even.most_common()),
        "big_small_dist": dict(big_small.most_common()),
        "zoro_rate": round(zoro / n, 4),
        "repeat_rate": round(repeat / n, 4),
        "sequential_rate": round(seq / n, 4),
    }


def _is_sequential(digits):
    """昇順/降順の連番（例 123 / 321 / 3456）か。"""
    asc = all(digits[i + 1] - digits[i] == 1 for i in range(len(digits) - 1))
    desc = all(digits[i] - digits[i + 1] == 1 for i in range(len(digits) - 1))
    return asc or desc


def shape_label(digits):
    """形の分類ラベル（ゾロ目/ダブル/連番/バラ）。"""
    if len(set(digits)) == 1:
        return "ゾロ目"
    if _is_sequential(digits):
        return "連番"
    if len(set(digits)) < len(digits):
        return "ダブル"
    return "バラ"


def analyze_position_pairs(draws, D):
    """隣接位置ペアの共起(10x10)＋ボックス組合せ頻度TOP。"""
    pairs = {}
    for p in range(D - 1):
        c = Counter()
        for d in draws:
            dg = d["digits"]
            c[(dg[p], dg[p + 1])] += 1
        pairs[f"{p}-{p+1}"] = {f"{a}-{b}": cnt for (a, b), cnt in c.most_common(20)}

    box = Counter(tuple(sorted(d["digits"])) for d in draws)
    n = len(draws)
    top_box = [{"combo": list(combo), "count": cnt, "percentage": round(cnt / n * 100, 3)}
               for combo, cnt in box.most_common(20)] if n else []
    return {"position_pairs": pairs, "top_box_combos": top_box}


def build_appearance_grid(draws, D):
    """出目表: 各位×0-9の出現回数・直近100回・最終出現回号。"""
    n = len(draws)
    grid = {str(p): {str(d): 0 for d in range(10)} for p in range(D)}
    recent_grid = {str(p): {str(d): 0 for d in range(10)} for p in range(D)}
    last_seen = {str(p): {str(d): None for d in range(10)} for p in range(D)}
    recent_cut = max(0, n - 100)
    for i, dr in enumerate(draws):
        for p in range(D):
            d = dr["digits"][p]
            grid[str(p)][str(d)] += 1
            last_seen[str(p)][str(d)] = dr["round"]
            if i >= recent_cut:
                recent_grid[str(p)][str(d)] += 1
    return {"grid": grid, "recent_grid": recent_grid, "last_seen": last_seen,
            "total_draws": n, "recent_window": min(100, n)}
