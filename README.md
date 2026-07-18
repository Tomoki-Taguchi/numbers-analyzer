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

seed に日付とゲーム名を含むため、同日・同ゲームの再実行は決定的（bit一致）。

## ローカル実行
```bash
pip install -r scripts/requirements.txt
python scripts/fetch_numbers.py --game all      # データ取得（初回は全件・数分）
python scripts/analyze_numbers.py --game all    # 分析＋予想
cd docs && python -m http.server 8137           # http://localhost:8137
```

## デプロイ
`main`/`master` の `docs/` を GitHub Pages で配信。データ更新は Actions の
「Update NUMBERS Data」ワークフロー（cron＋手動 `workflow_dispatch`）が自動で行う。
