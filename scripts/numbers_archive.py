#!/usr/bin/env python3
"""ナンバーズ アーカイブ / バックテスト

- 本番アーカイブ: ロト6同様、実行ごとに次回予想を1件保存し、時間とともに答え合わせが蓄積。
  ヒットは多型（straight/box/mini/位置一致）で判定。
- 軽量バックテスト: 初日から成績を見せるため、直近N回を RF/LSTM 抜きの統計モードで
  look-ahead 無しに再現し、ヒット率を集計（高速）。
"""

import json
from pathlib import Path

from numbers_common import PERIOD_SIZES
from numbers_predict import (
    compute_factors, effective_weights, weighted_base, _metrics,
    generate_prediction, generate_sum_target_prediction,
)
import numbers_stats as stats
from numbers_predict import simulate_random_baseline

STAT_MODES = ["balanced", "frequency_heavy", "recent_heavy", "pull_heavy", "cycle_heavy", "sum_target"]
BACKTEST_ROUNDS = 150  # 軽量バックテストで遡る回数


def load_archive(path: Path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_archive(path: Path, archive):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


def build_archive_entry(predicted_round, data_round, periods, period_labels, last_updated):
    """全期間×全モードの予想をコンパクトにアーカイブ化。"""
    entry = {
        "predicted_round": predicted_round,
        "data_up_to_round": data_round,
        "generated_at": last_updated,
        "actual": None,
        "verified": False,
        "predictions_by_period": {},
    }
    for pk, pdata in periods.items():
        modes = {}
        for mk, pred in pdata["predictions"].items():
            modes[mk] = {
                "mode_name": pred["mode_name"],
                "digits": pred["digits"],
                "number_str": pred["number_str"],
                "metrics": pred["metrics"],
                "straight_hit": None, "box_hit": None, "mini_hit": None,
                "set_hit": None, "position_match_count": None,
            }
        entry["predictions_by_period"][pk] = {"modes": modes}
    return entry


def _score_hit(pred_digits, actual_digits, has_mini):
    straight = pred_digits == actual_digits
    box = sorted(pred_digits) == sorted(actual_digits)
    mini = has_mini and pred_digits[-2:] == actual_digits[-2:]
    pm = sum(1 for a, b in zip(pred_digits, actual_digits) if a == b)
    return straight, box, mini, pm


def verify_archive(archive, all_draws, has_mini):
    """実際の結果が出たエントリの答え合わせ。"""
    by_round = {d["round"]: d for d in all_draws}
    for entry in archive:
        if entry.get("verified"):
            continue
        pr = entry["predicted_round"]
        draw = by_round.get(pr)
        if not draw:
            continue
        actual = draw["digits"]
        entry["actual"] = {"digits": actual, "date": draw["date"]}
        for pk, pdata in entry["predictions_by_period"].items():
            for mk, mode in pdata["modes"].items():
                st, bx, mn, pm = _score_hit(mode["digits"], actual, has_mini)
                mode["straight_hit"] = st
                mode["box_hit"] = bx
                mode["mini_hit"] = mn if has_mini else None
                mode["set_hit"] = st or bx
                mode["position_match_count"] = pm
        entry["verified"] = True


def calc_mode_stats(archive, D, has_mini):
    """期間×モードの累計成績＋位置一致分布＋理論ランダム基準。"""
    agg = {}
    total_by_period = {}
    for entry in archive:
        if not entry.get("verified"):
            continue
        for pk, pdata in entry["predictions_by_period"].items():
            total_by_period[pk] = total_by_period.get(pk, 0) + 1
            for mk, mode in pdata["modes"].items():
                key = (pk, mk)
                a = agg.setdefault(key, {
                    "mode_name": mode["mode_name"], "total": 0,
                    "straight": 0, "box": 0, "mini": 0, "set": 0,
                    "position_match_distribution": {str(k): 0 for k in range(D + 1)},
                    "best_position_match": 0,
                })
                a["total"] += 1
                a["straight"] += 1 if mode.get("straight_hit") else 0
                a["box"] += 1 if mode.get("box_hit") else 0
                a["mini"] += 1 if mode.get("mini_hit") else 0
                a["set"] += 1 if mode.get("set_hit") else 0
                pm = mode.get("position_match_count") or 0
                a["position_match_distribution"][str(pm)] += 1
                a["best_position_match"] = max(a["best_position_match"], pm)

    result = {}
    for (pk, mk), a in agg.items():
        t = a["total"] or 1
        result.setdefault(pk, {})[mk] = {
            **a,
            "straight_rate": round(a["straight"] / t * 100, 3),
            "box_rate": round(a["box"] / t * 100, 3),
            "set_rate": round(a["set"] / t * 100, 3),
            "mini_rate": round(a["mini"] / t * 100, 3) if has_mini else None,
        }
    # 期間ごとの理論基準
    baselines = {pk: simulate_random_baseline(total_by_period.get(pk, 0), D, has_mini)
                 for pk in result}
    return {"by_period": result, "random_baseline": baselines, "total_by_period": total_by_period}


def backfill_missing_archive(archive, all_draws, last_updated, compute_periods_fn):
    """アーカイブ開始以降に欠けた回を、その時点データで再構築（ロト6同様の範囲）。

    compute_periods_fn は (その時点までの draws, 予想対象の回号) を受け取る。
    回号を渡すのは、本番と同じ種で予想を再現するため（欠番があっても正しく対応付く）。
    """
    if not archive:
        return
    archived = {e["predicted_round"] for e in archive}
    draw_rounds = {d["round"] for d in all_draws}
    latest = all_draws[-1]["round"]
    missing = sorted(r for r in range(min(archived), latest + 1)
                     if r in draw_rounds and r not in archived)
    for r in missing:
        hist = [d for d in all_draws if d["round"] < r]
        if len(hist) < max(PERIOD_SIZES):
            continue
        print(f"Backfilling archive for round {r} (data up to {hist[-1]['round']})")
        periods, labels = compute_periods_fn(hist, r)
        archive.append(build_archive_entry(r, hist[-1]["round"], periods, labels, last_updated))


# ---- 軽量バックテスト（統計モードのみ・RF/LSTM抜き・高速） ----

def _uniform_ai(D):
    return {"per_position": {str(p): {str(d): 0.1 for d in range(10)} for p in range(D)}}


def run_backtest(all_draws, D, game_cfg, n_rounds=BACKTEST_ROUNDS, seed_key_fn=None):
    """直近 n_rounds を統計モードで look-ahead 無しに再現し、ヒット率を集計。

    RF/LSTM は一様スコア（=ランキングに影響しない）を渡し、統計モードのみ評価する。
    予想は全期間(all)の分析で生成（安定重視）。高速（モデル学習なし）。

    seed_key_fn は回号から予想の種を作る関数（本番と同じもの）。各回を本番と同じ
    種で再現するために渡す。未指定なら固定種で全回を回す。
    """
    has_mini = game_cfg["has_mini"]
    total = len(all_draws)
    start = max(max(PERIOD_SIZES), total - n_rounds)
    agg = {mk: {"total": 0, "straight": 0, "box": 0, "mini": 0, "set": 0,
                "position_match_distribution": {str(k): 0 for k in range(D + 1)}}
           for mk in STAT_MODES}

    for i in range(start, total):
        hist = all_draws[:i]
        actual = all_draws[i]["digits"]
        seed_key = seed_key_fn(all_draws[i]["round"]) if seed_key_fn else "backtest"
        freq = stats.analyze_frequency(hist, D)
        cyc = stats.analyze_cycle(hist, D)
        dsum = stats.analyze_digit_sum(hist, D)
        ai = _uniform_ai(D)
        base_data = compute_factors(freq, cyc, ai, ai, hist, D)
        for mk in STAT_MODES:
            if mk == "sum_target":
                pred = generate_sum_target_prediction(
                    base_data, dsum, freq, cyc, ai, ai, hist, D, game_cfg, "all", seed_key, mc_trials=0)
            else:
                pred = generate_prediction(
                    base_data, freq, cyc, ai, ai, hist, D, game_cfg, mk, "all", seed_key, mc_trials=0)
            st, bx, mn, pm = _score_hit(pred["digits"], actual, has_mini)
            a = agg[mk]
            a["total"] += 1
            a["straight"] += 1 if st else 0
            a["box"] += 1 if bx else 0
            a["mini"] += 1 if mn else 0
            a["set"] += 1 if (st or bx) else 0
            a["position_match_distribution"][str(pm)] += 1

    rounds_tested = total - start
    modes_out = {}
    for mk, a in agg.items():
        t = a["total"] or 1
        modes_out[mk] = {
            **a,
            "straight_rate": round(a["straight"] / t * 100, 3),
            "box_rate": round(a["box"] / t * 100, 3),
            "set_rate": round(a["set"] / t * 100, 3),
            "mini_rate": round(a["mini"] / t * 100, 3) if has_mini else None,
        }
    return {
        "rounds_tested": rounds_tested,
        "range": f"第{all_draws[start]['round']}回〜第{all_draws[-1]['round']}回" if rounds_tested else "",
        "modes": modes_out,
        "random_baseline": simulate_random_baseline(rounds_tested, D, has_mini),
        "note": "統計モードのみ・RF/LSTM除外・look-ahead無し(全期間分析で生成)。AI含む実成績はアーカイブに蓄積。",
    }
