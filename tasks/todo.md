# ナンバーズ3・ナンバーズ4 アナライザー タスク

データ元: 楽天×宝くじ `takarakuji.rakuten.co.jp/backnumber/numbers{3,4}_detail/XXXX-YYYY/`（20回単位）
中核: 各位0-9のD×10行列。D=3(N3)/4(N4)を`--game`で切替。

## Phase 1: 雛形
- [x] ディレクトリ作成・git init
- [x] データ元HTML構造の実地確認（detailグループが最新まで／404で終端）
- [ ] requirements.txt / .gitignore / README

## Phase 2: fetch_numbers.py
- [ ] 楽天スクレイパ（detailグループ巡回・差分更新・欠番検出）
- [ ] N3全件取得・検証（先頭ゼロ保持）
- [ ] N4全件取得・検証

## Phase 3: analyze_numbers.py（統計）
- [ ] frequency（各位＋全体）/ appearance_grid（出目表）
- [ ] pull（位置別引っ張り）/ digit_sum / shape / cycle / position_pairs
- [ ] JSON出力目視検証

## Phase 4: analyze_numbers.py（AI予想）
- [ ] RF（各位10クラス）/ LSTM（各位one-hot）
- [ ] monte_carlo / random_baseline / 予想モード / sum_target
- [ ] 決定性（同入力bit一致）検証

## Phase 5: フロントエンド
- [ ] index.html（N3/N4切替＋期間スライダー＋タブ）
- [ ] app.js / style.css
- [ ] ローカル配信で全タブ描画確認

## Phase 6: アーカイブ/成績
- [ ] build/verify/mode_stats（straight/box/mini/位置一致）
- [ ] バックテスト集計確認

## Phase 7: CI＋Pages
- [ ] update.yml（matrix N3/N4）
- [ ] GitHub public repo作成・push・Pages有効化
- [ ] gh workflow runで初回フル生成・ライブ確認

## レビュー
（完了後に記入）
