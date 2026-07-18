#!/usr/bin/env python3
"""ナンバーズ3 / ナンバーズ4 分析＋AI予想エンジン（オーケストレーション）

    python analyze_numbers.py --game numbers3
    python analyze_numbers.py --game numbers4
    python analyze_numbers.py --game all

各期間（直近100〜1000＋全期間）で統計分析・RF/LSTM・予想を計算し、
analysis_numbers{3,4}.json を出力。アーカイブと軽量バックテストも同梱。
"""

import argparse
from datetime import date

from numbers_common import GAMES, PERIOD_SIZES, load_data
import numbers_stats as stats
from numbers_ai import predict_rf, predict_lstm
from numbers_predict import compute_factors, run_predictions
import numbers_archive as arc


def _date_str():
    # 決定性のため実行日を種にする（同日・同ゲームは同結果）
    return date.today().isoformat()


def analyze_period(draws, D, game_cfg, period_label, date_str):
    """1期間分の分析＋予想を計算して返す。"""
    freq = stats.analyze_frequency(draws, D)
    grid = stats.build_appearance_grid(draws, D)
    pull = stats.analyze_pull(draws, D)
    dsum = stats.analyze_digit_sum(draws, D)
    shape = stats.analyze_shape(draws, D)
    pairs = stats.analyze_position_pairs(draws, D)
    cycle = stats.analyze_cycle(draws, D)
    rf = predict_rf(draws, D)
    lstm = predict_lstm(draws, D)

    base_data = compute_factors(freq, cycle, rf, lstm, draws, D)
    predictions = run_predictions(
        base_data, freq, cycle, rf, lstm, dsum, draws, D, game_cfg, period_label, date_str)

    # 出力用に band_weights（内部用）を除去
    dsum_out = {k: v for k, v in dsum.items() if k != "band_weights"}

    recent = [{
        "round": d["round"], "date": d["date"], "digits": d["digits"],
        "sum": sum(d["digits"]),
        "odd_even": f"{sum(1 for x in d['digits'] if x % 2 == 1)}:{D - sum(1 for x in d['digits'] if x % 2 == 1)}",
        "shape": stats.shape_label(d["digits"]),
    } for d in draws[-20:][::-1]]

    return {
        "frequency": freq,
        "appearance_grid": grid,
        "pull": pull,
        "digit_sum": dsum_out,
        "shape": shape,
        "position_pairs": pairs["position_pairs"],
        "top_box_combos": pairs["top_box_combos"],
        "cycle": cycle,
        "rf_scores": rf,
        "lstm_scores": lstm,
        "predictions": predictions,
        "summary_stats": {
            "total_draws": len(draws),
            "avg_sum": dsum["avg"],
            "sum_std": dsum["std"],
            "date_range": f"{draws[0]['date']}〜{draws[-1]['date']}" if draws else "",
        },
        "recent_draws": recent,
    }


def compute_periods(draws, D, game_cfg, date_str):
    """全期間＋各直近N回の分析・予想を計算し、(periods, period_labels) を返す。"""
    periods = {"all": analyze_period(draws, D, game_cfg, "all", date_str)}
    for size in PERIOD_SIZES:
        if len(draws) < size:
            continue
        periods[str(size)] = analyze_period(draws[-size:], D, game_cfg, str(size), date_str)

    period_labels = []
    for size in PERIOD_SIZES:
        if str(size) in periods:
            pd = draws[-size:]
            period_labels.append({
                "key": str(size), "label": f"直近{size}回",
                "range": f"第{pd[0]['round']}回〜第{pd[-1]['round']}回", "draws": size,
            })
    period_labels.append({
        "key": "all", "label": "全期間",
        "range": f"第{draws[0]['round']}回〜第{draws[-1]['round']}回" if draws else "",
        "draws": len(draws),
    })
    return periods, period_labels


def run(game: str):
    import json
    game_cfg = GAMES[game]
    D = game_cfg["digits"]
    date_str = _date_str()
    print(f"=== {game_cfg['label']} Analyzer ===")

    draws = load_data(game_cfg)
    print(f"Loaded {len(draws)} draws (第{draws[0]['round']}回〜第{draws[-1]['round']}回)")

    print("--- 全期間＋各直近N回の分析・予想 ---")
    periods, period_labels = compute_periods(draws, D, game_cfg, date_str)

    # アーカイブ
    archive_path = game_cfg["archive_path"]
    archive = arc.load_archive(archive_path)
    latest_round = draws[-1]["round"]
    next_round = latest_round + 1
    last_updated = date_str

    arc.backfill_missing_archive(
        archive, draws, last_updated,
        compute_periods_fn=lambda hist: compute_periods(hist, D, game_cfg, date_str))
    arc.verify_archive(archive, draws, game_cfg["has_mini"])

    existing = next((e for e in archive if e["predicted_round"] == next_round), None)
    entry = arc.build_archive_entry(next_round, latest_round, periods, period_labels, last_updated)
    if existing is None:
        archive.append(entry)
        print(f"Archived predictions for round {next_round}")
    elif not existing.get("verified"):
        archive[archive.index(existing)] = entry
        print(f"Refreshed pending predictions for round {next_round}")
    archive.sort(key=lambda e: e["predicted_round"])
    arc.save_archive(archive_path, archive)

    mode_stats = arc.calc_mode_stats(archive, D, game_cfg["has_mini"])

    print("--- 軽量バックテスト（統計モード・直近{}回） ---".format(arc.BACKTEST_ROUNDS))
    backtest = arc.run_backtest(draws, D, game_cfg, date_str=date_str)
    print(f"  backtest rounds: {backtest['rounds_tested']}")

    output = {
        "last_updated": last_updated,
        "game": game,
        "digits": D,
        "latest_round": latest_round,
        "position_labels": game_cfg["positions"],
        "period_labels": period_labels,
        "periods": periods,
        "archive": archive,
        "mode_stats": mode_stats,
        "backtest": backtest,
    }
    out_path = game_cfg["output_path"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Saved analysis to {out_path}")

    # サマリ表示
    allp = periods["all"]["predictions"]
    print("全期間の予想:")
    for mk, pred in allp.items():
        print(f"  {pred['mode_name']}: {pred['number_str']}  (sum={pred['metrics']['sum']}, {pred['metrics']['shape']})")


def main():
    parser = argparse.ArgumentParser(description="ナンバーズ3/4 分析＋AI予想")
    parser.add_argument("--game", choices=["numbers3", "numbers4", "all"], default="all")
    args = parser.parse_args()
    games = ["numbers3", "numbers4"] if args.game == "all" else [args.game]
    for g in games:
        run(g)
        print()


if __name__ == "__main__":
    main()
