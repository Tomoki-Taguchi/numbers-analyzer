# 🔢 NUMBERS ANALYZER

ナンバーズ3・ナンバーズ4の統計分析 × AI予想サイト（GitHub Pages）。
[loto6-analyzer](https://github.com/Tomoki-Taguchi/loto6-analyzer) の姉妹プロジェクト。

> ⚠️ 娯楽用途です。ナンバーズは各位0〜9がほぼ一様な「ほぼ記憶のない」ゲームで、
> 本ツールは将来の当選を予測・保証しません。購入は自己責任で。

## 構成

```
docs/                     # GitHub Pages 配信ルート
  index.html / app.js / style.css
  data/
    numbers3_data.json / numbers4_data.json          # 生データ {round,date,digits[]}
    analysis_numbers3.json / analysis_numbers4.json  # 分析＋予想＋成績
    archive_numbers3.json / archive_numbers4.json    # 予想アーカイブ（答え合わせ蓄積）
scripts/
  fetch_numbers.py        # 楽天×宝くじ スクレイパ（--game）
  add_draw.py             # 抽選結果の手入力（発表当日にデータへ1回分を追記）
  analyze_numbers.py      # 分析＋AI予想エンジン（--game）
  numbers_common.py / numbers_stats.py / numbers_ai.py
  numbers_predict.py / numbers_archive.py
.github/workflows/update.yml   # 平日抽選の翌朝に自動更新（N3/N4 並列）
```

## データ元
楽天×宝くじ `takarakuji.rakuten.co.jp/backnumber/numbers{3,4}_detail/`（20回単位・第1回1994年〜）。
差分更新・欠番検出対応。

## 分析・予想の中身
- **各位頻度／出目表**: 位ごとの0〜9出現回数（ホット・コールド）
- **引っ張り**: 同じ位置で同じ数字が続く傾向
- **合計値・形**: 合計分布、奇偶/大小、ゾロ目/連番、ボックス組合せ
- **AI予想**: 各位ごとに RandomForest / LSTM で0〜9を予測。7モード（総合/頻度/直近/引っ張り/周期/AI/合計値）
- **モンテカルロ信頼度**: 各位を重み付き1万回抽選し、ストレート/ボックス/ミニ確率を算出
- **成績**: 直近150回の統計モード・バックテスト＋アーカイブ実成績（時間とともに蓄積）

seed に**予想対象の回号**とゲーム名を含むため、同じ回号・同じゲームなら何度実行しても
決定的（bit一致）。実行日に依存しないので、抽選結果を手入力して当日夜に出した予想と、
翌朝の自動更新が出す予想は一致する。

## ローカル実行
```bash
pip install -r scripts/requirements.txt
python scripts/fetch_numbers.py --game all      # データ取得（初回は全件・数分）
python scripts/analyze_numbers.py --game all    # 分析＋予想
cd docs && python -m http.server 8137           # http://localhost:8137
```

## 更新タイミング
| | いつ |
|---|---|
| ナンバーズの抽選結果発表 | 平日（月〜金）**当日 18:45頃** |
| サイトへの自動反映 | **翌朝 JST 9:00頃**（Actions の cron） |

## 抽選日の夜に次回予想を出す（手入力）
自動更新は翌朝なので、当日夜に予想を見たいときは当選番号を手入力する。

**GitHub の画面から**（推奨・ローカル環境不要）
Actions →「Update NUMBERS Data」→ Run workflow → 当選番号を入力して実行。
取得・分析・push まで走ってサイトに反映される。N3 / N4 は片方だけの入力でもよい。

**ローカルで**
```bash
python scripts/add_draw.py --game numbers3 --digits 388   # 先頭ゼロ可: 019
python scripts/analyze_numbers.py --game numbers3
```

手入力した回号は翌朝の `fetch_numbers.py` が公式データで上書きするため、
打ち間違えても自動的に訂正される。

## デプロイ
`main`/`master` の `docs/` を GitHub Pages で配信。データ更新は Actions の
「Update NUMBERS Data」ワークフロー（cron＋手動 `workflow_dispatch`）が自動で行う。
