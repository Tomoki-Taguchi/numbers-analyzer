# ナンバーズ3・ナンバーズ4 アナライザー タスク

データ元: 楽天×宝くじ `takarakuji.rakuten.co.jp/backnumber/numbers{3,4}_detail/XXXX-YYYY/`（20回単位）
中核: 各位0-9のD×10行列。D=3(N3)/4(N4)を`--game`で切替。

## Phase 1: 雛形
- [x] ディレクトリ作成・git init
- [x] データ元HTML構造の実地確認（detailグループが最新まで／404で終端）
- [x] requirements.txt / .gitignore / README

## Phase 2: fetch_numbers.py
- [x] 楽天スクレイパ（detailグループ巡回・差分更新・欠番検出）
- [x] N3全件取得・検証（7029件・欠番0・先頭ゼロ保持）
- [x] N4全件取得・検証（7029件・欠番0）

## Phase 3: analyze_numbers.py（統計）
- [x] frequency（各位＋全体）/ appearance_grid（出目表）
- [x] pull（位置別引っ張り）/ digit_sum / shape / cycle / position_pairs
- [x] JSON出力検証（各位合計=総回数, N3 sum≈13.6/N4≈18.1）

## Phase 4: analyze_numbers.py（AI予想）
- [x] RF（各位10クラス）/ LSTM（各位one-hot）
- [x] monte_carlo / random_baseline / 予想モード7種 / sum_target
- [x] 決定性（同入力bit一致=BITMATCH_OK, 6桁丸めで浮動小数ノイズ吸収）

## Phase 5: フロントエンド
- [x] index.html（N3/N4切替＋期間スライダー＋9タブ）
- [x] app.js / style.css（Chart.js SRI付き）
- [x] ローカル配信で全タブ描画確認（コンソールエラー0）

## Phase 6: アーカイブ/成績
- [x] build/verify/mode_stats（straight/box/mini/位置一致）
- [x] 軽量バックテスト（統計モード直近150回・look-ahead無し）

## Phase 7: CI＋Pages
- [x] update.yml（matrix N3/N4・push競合対策rebase）
- [x] GitHub public repo作成・push・Pages有効化（ライブ200・描画確認済）
- [~] gh workflow run（CIパイプライン検証・実行中）

## Phase 8: 抽選結果の手入力（当日夜に次回予想を出す）
発表は当日18:45頃だが自動更新は翌朝9時。その差を埋める。
- [x] add_draw.py（手入力・桁数/回号/欠番の検証・`--if-missing`で取得済みなら空振り）
- [x] 予想の種を実行日→**予想対象の回号**へ変更（手入力の予想が翌朝に上書きされない）
- [x] backfill/backtest も回号ベースの種に統一（本番と同じ予想を再現）
- [x] update.yml に `workflow_dispatch` 入力（N3/N4/抽選日）を追加。取得→手入力の順
- [x] 検証: 回号ごとの決定性 / 別回号で変化 / 欠番時も回号がずれない / E2E（AIスタブ）
- [ ] 実運用で1回まわす（Actions手動実行 → サイト反映確認）

## レビュー
- ライブ: https://tomoki-taguchi.github.io/numbers-analyzer/
- リポジトリ: https://github.com/Tomoki-Taguchi/numbers-analyzer
- 実装: fetch/analyze を6モジュールに分割（各<800行規約遵守）
- 正直さ: ナンバーズはほぼ記憶なし→頻度/hot-coldは弱信号。バックテストのstraight率≈ランダム基準(0.1%/0.01%)。免責・弱シグナルをUIに明記
- 未確認: 初回スケジュール実行までアーカイブ実成績は空（設計通り時間とともに蓄積）
