#!/usr/bin/env python3
"""ナンバーズ3 / ナンバーズ4 データスクレイピング

データ元: 楽天×宝くじ (takarakuji.rakuten.co.jp)
  詳細ページ: /backnumber/numbers{3,4}_detail/XXXX-YYYY/  (20回単位・最古〜最新まで一様)
  一覧ページ: /backnumber/numbers{3,4}_past/            (最新回の把握に使用)

各詳細ページは「回号 / 抽せん日 / 当選番号」の3列テーブル1つ。
当選番号は先頭ゼロを保持した固定桁の文字列 (例 N3:"019", N4:"0149")。

使い方:
    python fetch_numbers.py --game numbers3
    python fetch_numbers.py --game numbers4
    python fetch_numbers.py --game all
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    print("beautifulsoup4 が必要です: pip install beautifulsoup4 lxml", file=sys.stderr)
    raise

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"

GAMES = {
    "numbers3": {
        "digits": 3,
        "label": "ナンバーズ3",
        "detail_url": "https://takarakuji.rakuten.co.jp/backnumber/numbers3_detail/{start:04d}-{end:04d}/",
        "index_url": "https://takarakuji.rakuten.co.jp/backnumber/numbers3_past/",
        "data_path": DATA_DIR / "numbers3_data.json",
    },
    "numbers4": {
        "digits": 4,
        "label": "ナンバーズ4",
        "detail_url": "https://takarakuji.rakuten.co.jp/backnumber/numbers4_detail/{start:04d}-{end:04d}/",
        "index_url": "https://takarakuji.rakuten.co.jp/backnumber/numbers4_past/",
        "data_path": DATA_DIR / "numbers4_data.json",
    },
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NumbersAnalyzer/1.0)"}
REQUEST_DELAY = 1.2  # 連続リクエスト間の待機秒数
GROUP_SIZE = 20      # 詳細ページ1枚あたりの回数


def group_bounds(round_num: int) -> tuple[int, int]:
    """回号が属する詳細グループ (start, end) を返す。例: 191 -> (181, 200)。"""
    start = ((round_num - 1) // GROUP_SIZE) * GROUP_SIZE + 1
    return start, start + GROUP_SIZE - 1


def load_existing_data(path: Path) -> dict:
    """既存データを読み込む。なければ空データを返す。"""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": None, "total_draws": 0, "draws": []}


def _soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _get(url: str) -> Optional[requests.Response]:
    """GET。404 は None、その他のエラーは1回リトライ。"""
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"  {'Retry' if attempt == 0 else 'Error'}: {url} -> {e}")
            if attempt == 0:
                time.sleep(3)
    return None


def parse_detail_page(html: str, digits: int) -> list[dict]:
    """詳細ページ(1グループ)から抽選データをパースする。"""
    soup = _soup(html)
    draws = []
    for row in soup.select("table tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        round_text = cells[0].get_text(" ", strip=True)
        round_match = re.search(r"第(\d+)回", round_text)
        if not round_match:
            continue  # ヘッダー行など
        round_num = int(round_match.group(1))

        date_text = cells[1].get_text(" ", strip=True)
        date_match = re.search(r"(\d{4})[/-](\d{2})[/-](\d{2})", date_text)
        date_str = "-".join(date_match.groups()) if date_match else "unknown"

        # 当選番号: 先頭ゼロを保持したいので int 化せず文字単位で分解する
        num_text = cells[2].get_text(" ", strip=True)
        num_digits = re.sub(r"\D", "", num_text)
        if not num_digits or len(num_digits) > digits:
            continue
        num_digits = num_digits.zfill(digits)  # "19" -> "019" のような取りこぼし対策
        digit_list = [int(c) for c in num_digits]

        if len(digit_list) != digits or not all(0 <= d <= 9 for d in digit_list):
            continue

        draws.append({"round": round_num, "date": date_str, "digits": digit_list})

    return draws


def find_latest_round(game_cfg: dict) -> int:
    """一覧ページから最新回号を取得する。失敗時は 0。"""
    resp = _get(game_cfg["index_url"])
    if resp is None:
        return 0
    rounds = [int(x) for x in re.findall(r"第(\d{3,6})回", resp.text)]
    return max(rounds) if rounds else 0


def _fetch_group(game_cfg: dict, start: int, end: int) -> Optional[list]:
    url = game_cfg["detail_url"].format(start=start, end=end)
    print(f"Fetching {start:04d}-{end:04d}: {url}")
    resp = _get(url)
    if resp is None:
        return None
    return parse_detail_page(resp.text, game_cfg["digits"])


def fetch_all(game_cfg: dict, existing_last_round: int = 0) -> list[dict]:
    """詳細グループを巡回して抽選データを取得する。

    差分更新時は既存最終回のグループから最新グループへ向かって取得する。
    """
    latest = find_latest_round(game_cfg)
    if latest <= 0:
        print("  ⚠️  最新回号を特定できませんでした。1回目から順に取得します。")
        latest = existing_last_round + GROUP_SIZE  # 保守的な下限

    start_round = existing_last_round + 1 if existing_last_round > 0 else 1
    first_group_start = group_bounds(start_round)[0]
    last_group_start = group_bounds(latest)[0]

    all_draws = []
    g = first_group_start
    while g <= last_group_start:
        start, end = g, g + GROUP_SIZE - 1
        draws = _fetch_group(game_cfg, start, end)
        if draws is None:
            print(f"  グループ {start:04d}-{end:04d} は取得できませんでした(404?)。停止します。")
            break
        if draws:
            print(f"  {len(draws)}件 (第{draws[0]['round']}回〜第{draws[-1]['round']}回)")
            all_draws.extend(draws)
        g += GROUP_SIZE
        time.sleep(REQUEST_DELAY)

    return all_draws


def save(game: str, game_cfg: dict, all_draws: list[dict], new_count: int) -> None:
    # 欠番検出: 取得元の掲載漏れ等で回号が飛ぶことがあるため警告のみ行う。
    if all_draws:
        present = {d["round"] for d in all_draws}
        rounds = sorted(present)
        gaps = [r for r in range(rounds[0], rounds[-1] + 1) if r not in present]
        if gaps:
            head = gaps[:20]
            print(f"⚠️  欠番を検出: 第{rounds[0]}回〜第{rounds[-1]}回のうち {len(gaps)} 回が欠落: {head}{' ...' if len(gaps) > 20 else ''}")
        else:
            print(f"✓ 回号は連続しています（第{rounds[0]}回〜第{rounds[-1]}回、{len(all_draws)}件）")

    output = {
        "last_updated": datetime.now().isoformat(),
        "game": game,
        "digits": game_cfg["digits"],
        "total_draws": len(all_draws),
        "draws": all_draws,
    }
    game_cfg["data_path"].parent.mkdir(parents=True, exist_ok=True)
    with open(game_cfg["data_path"], "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(all_draws)} draws to {game_cfg['data_path']}")
    print(f"New draws added: {new_count}")


def run(game: str) -> None:
    game_cfg = GAMES[game]
    print(f"=== {game_cfg['label']} Data Fetcher ===")
    existing = load_existing_data(game_cfg["data_path"])
    existing_rounds = {d["round"] for d in existing["draws"]}
    last_round = max(existing_rounds) if existing_rounds else 0
    print(f"Existing data: {len(existing_rounds)} draws, last round: {last_round}")

    new_draws = fetch_all(game_cfg, last_round)
    print(f"\nFetched {len(new_draws)} draws this run")

    merged = {d["round"]: d for d in existing["draws"]}
    new_count = 0
    for d in new_draws:
        if d["round"] not in merged:
            new_count += 1
        merged[d["round"]] = d
    all_draws = sorted(merged.values(), key=lambda x: x["round"])

    save(game, game_cfg, all_draws, new_count)


def main() -> None:
    parser = argparse.ArgumentParser(description="ナンバーズ3/4 データ取得")
    parser.add_argument("--game", choices=["numbers3", "numbers4", "all"], default="all")
    args = parser.parse_args()

    games = ["numbers3", "numbers4"] if args.game == "all" else [args.game]
    for g in games:
        run(g)
        print()


if __name__ == "__main__":
    main()
