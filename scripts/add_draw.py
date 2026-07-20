#!/usr/bin/env python3
"""抽選結果の手入力（スクレイパを待たずにデータへ1回分を追記する）

ナンバーズの当選番号は抽選日の 18:45 頃に発表されるが、自動更新ワークフローは
翌朝(JST 9:00頃)に走る。その差を埋めて「今夜のうちに次回予想を出す」ための入口。

手入力した回号は、翌朝の fetch_numbers.py が同じ回号を公式データで上書きするため、
打ち間違えても自動的に訂正される。

使い方:
    python add_draw.py --game numbers3 --digits 388
    python add_draw.py --game numbers4 --digits 0149 --date 2026-07-20
    python add_draw.py --game numbers3 --digits 019 --round 7030 --force

追記後は analyze_numbers.py を実行すると次回予想が更新される。
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from numbers_common import GAMES

# 抽選・発表は日本時間基準。実行環境が UTC(GitHub Actions) でも日付がずれないようにする。
JST = timezone(timedelta(hours=9))


def _today_jst() -> str:
    return datetime.now(JST).date().isoformat()


def parse_digits(raw: str, expected: int) -> list[int]:
    """当選番号文字列を桁リストへ。先頭ゼロを保持するため int 化せず文字単位で扱う。"""
    cleaned = "".join(ch for ch in raw if ch.isdigit())
    if len(cleaned) != len(raw.strip()):
        raise ValueError(f"数字以外の文字が含まれています: {raw!r}")
    if len(cleaned) != expected:
        raise ValueError(f"{expected}桁で入力してください（入力: {raw!r} = {len(cleaned)}桁）")
    return [int(c) for c in cleaned]


def validate_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"日付は YYYY-MM-DD 形式で指定してください: {date_str!r}")
    if d.weekday() >= 5:  # ナンバーズは平日抽選
        print(f"⚠️  {date_str} は{'土日'[d.weekday() - 5]}曜です。ナンバーズは平日抽選のため日付を確認してください。")
    return date_str


def add_draw(game: str, digits: list[int], date_str: str, round_num: Optional[int],
             force: bool, if_missing: bool = False) -> tuple[Optional[int], dict]:
    """データへ1回分を追記し、(回号, 保存内容) を返す。

    if_missing 指定時、同じ抽選日の回が既にあれば何もせず (None, data) を返す。
    スクレイパが先に取り込んでいた場合に手入力を空振りさせるための入口。
    """
    game_cfg = GAMES[game]
    path = game_cfg["data_path"]
    if not path.exists():
        raise FileNotFoundError(f"{path} がありません。先に fetch_numbers.py を実行してください。")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    draws = {d["round"]: d for d in data["draws"]}
    last_round = max(draws) if draws else 0
    target = round_num if round_num is not None else last_round + 1

    if if_missing:
        same_date = next((d for d in draws.values() if d["date"] == date_str), None)
        if same_date is not None:
            return None, data

    # 回号の整合性チェック。取り違えは分析結果を静かに歪めるので既定では止める。
    if target in draws and not force:
        cur = draws[target]
        raise ValueError(
            f"第{target}回は既に登録済みです（{cur['date']} {''.join(map(str, cur['digits']))}）。"
            f"上書きするなら --force を付けてください。")
    if target > last_round + 1 and not force:
        raise ValueError(
            f"第{last_round + 1}回〜第{target - 1}回が欠番になります"
            f"（最終登録は第{last_round}回）。意図的なら --force を付けてください。")

    draws[target] = {"round": target, "date": date_str, "digits": digits}
    all_draws = sorted(draws.values(), key=lambda x: x["round"])

    data["last_updated"] = datetime.now().isoformat()
    data["total_draws"] = len(all_draws)
    data["draws"] = all_draws
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return target, data


def main() -> None:
    parser = argparse.ArgumentParser(description="ナンバーズ抽選結果の手入力")
    parser.add_argument("--game", choices=["numbers3", "numbers4"], required=True)
    parser.add_argument("--digits", required=True,
                        help="当選番号（N3は3桁 / N4は4桁。先頭ゼロ可: 019）")
    parser.add_argument("--date", default=None, help="抽選日 YYYY-MM-DD（既定: 今日(JST)）")
    parser.add_argument("--round", type=int, default=None,
                        help="回号（既定: 最終回号+1）")
    parser.add_argument("--force", action="store_true",
                        help="既存回号の上書き・欠番の発生を許可する")
    parser.add_argument("--if-missing", action="store_true",
                        help="同じ抽選日が既に取り込まれていれば何もせず正常終了する")
    args = parser.parse_args()

    game_cfg = GAMES[args.game]
    try:
        digits = parse_digits(args.digits, game_cfg["digits"])
        date_str = validate_date(args.date) if args.date else _today_jst()
        target, data = add_draw(args.game, digits, date_str, args.round,
                                args.force, args.if_missing)
    except (ValueError, FileNotFoundError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    if target is None:
        print(f"= {game_cfg['label']} {date_str} は取得済みのため手入力をスキップしました")
        return

    num = "".join(str(d) for d in digits)
    print(f"✓ {game_cfg['label']} 第{target}回 {date_str} → {num} を登録しました"
          f"（全{data['total_draws']}件）")
    print(f"  次: python analyze_numbers.py --game {args.game}")


if __name__ == "__main__":
    main()
