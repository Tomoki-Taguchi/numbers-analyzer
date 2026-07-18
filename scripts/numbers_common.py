#!/usr/bin/env python3
"""ナンバーズ分析エンジン 共通定義

- GAMES: N3/N4 のゲーム設定（桁数D・位取りラベル・入出力パス・ミニ有無）
- 期間・多様性などの定数
- load_data / normalize / _seed_from_str などの共有ヘルパ
"""

import hashlib
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"

# 分析期間: 直近100〜1000(100刻み) + 全期間
PERIOD_SIZES = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]

GAMES = {
    "numbers3": {
        "digits": 3,
        "label": "ナンバーズ3",
        "positions": ["百の位", "十の位", "一の位"],
        "sum_max": 27,
        "has_mini": True,
        "data_path": DATA_DIR / "numbers3_data.json",
        "output_path": DATA_DIR / "analysis_numbers3.json",
        "archive_path": DATA_DIR / "archive_numbers3.json",
    },
    "numbers4": {
        "digits": 4,
        "label": "ナンバーズ4",
        "positions": ["千の位", "百の位", "十の位", "一の位"],
        "sum_max": 36,
        "has_mini": False,
        "data_path": DATA_DIR / "numbers4_data.json",
        "output_path": DATA_DIR / "analysis_numbers4.json",
        "archive_path": DATA_DIR / "archive_numbers4.json",
    },
}

# 予想の重み（モードごとにベースを複製して調整）
# ナンバーズは記憶なしに近く、引っ張り(前回反復)は「予測力」を持たない。重みを付けると
# 引っ張りが不自然に多発するため、pull は極小にして自然な基準率(各位≈10%)で現れるようにする。
BASE_WEIGHTS = {
    "freq": 1.0,     # 全期間の各位頻度
    "recent": 1.2,   # 直近トレンド
    "drought": 0.7,  # 未出（各位の平均間隔比）
    "pull": 0.1,     # 引っ張り（同位置反復）— 総合予想で基準率(≈1/3)になるよう極小
    "cycle": 0.8,    # 周期
    "rf": 1.2,       # RandomForest
    "lstm": 1.2,     # LSTM
}

# 各モードが提示する予想数字の個数
N_PREDICTIONS = 10

# 各モードの重み調整（signature 因子を強調）。pull は base が小さいので倍率を大きめに。
MODE_WEIGHTS = {
    "balanced": {},
    "frequency_heavy": {"freq": 2.2, "recent": 1.4},
    "recent_heavy": {"recent": 2.4},
    "pull_heavy": {"pull": 12.0, "recent": 1.3},
    "cycle_heavy": {"cycle": 2.6},
    "ml_heavy": {"rf": 2.4, "lstm": 2.4},
}

MODE_NAMES = {
    "balanced": "総合予想",
    "frequency_heavy": "出現頻度重視",
    "recent_heavy": "直近トレンド重視",
    "pull_heavy": "引っ張り重視",
    "cycle_heavy": "周期重視",
    "ml_heavy": "AI(RF+LSTM)重視",
    "sum_target": "合計値ターゲット予想",
}

# モードごとの「echo指標」を守る署名因子（多様性処理で保護する因子）
MODE_SIGNATURE = {
    "balanced": set(),
    "frequency_heavy": {"freq"},
    "recent_heavy": {"recent"},
    "pull_heavy": {"pull"},
    "cycle_heavy": {"cycle"},
    "ml_heavy": {"rf", "lstm"},
}

# 相関の高い echo 指標（多様性処理で重複加点を削る対象）
ECHO_FACTORS = {"freq", "recent", "cycle", "rf", "lstm"}
ECHO_REDUCTION = 0.7    # 非署名のecho因子を削る割合（大きいほどモード間の予想が分散）
DIVERSITY_JITTER = 0.02  # 予想トライアルに加える揺らぎ量
QUALITY_W = 0.6          # トライアル選定における平均スコアの重み

DIGIT_SUM_RECENT_BLEND = 0.35  # 合計値帯の重み: 直近ウィンドウの混合比


def load_data(game_cfg: dict) -> list[dict]:
    """生データを読み込み、回号昇順の draws を返す。"""
    path = game_cfg["data_path"]
    if not path.exists():
        raise FileNotFoundError(f"{path} がありません。先に fetch_numbers.py を実行してください。")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return sorted(data["draws"], key=lambda d: d["round"])


def normalize(values: dict) -> dict:
    """辞書の値を 0..1 に min-max 正規化する。全て同値なら 0.5。"""
    if not values:
        return {}
    vs = list(values.values())
    lo, hi = min(vs), max(vs)
    if hi - lo < 1e-12:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def _seed_from_str(s: str) -> int:
    """文字列から決定的な整数シードを作る。"""
    return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:8], 16)


def digit_sum(digits: list[int]) -> int:
    return sum(digits)


def sum_range_for(digits: int) -> tuple[int, int]:
    return 0, digits * 9
