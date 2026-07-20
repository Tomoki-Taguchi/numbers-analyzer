# Lessons

このプロジェクトで受けた修正・失敗から学んだパターンを記録する。
セッション開始時にレビューし、同じミスを繰り返さない。

---

## 2026-07-20: HTMLの`<script src>`にクエリを付ける編集で閉じタグを落とした

**症状**: GitHub Pagesで「動かない」。app.jsの関数が全て`undefined`、予想もボタンも何も描画されず。

**原因**: `<script src="app.js"></script>` にバージョンクエリを付ける編集で、`</script>` 閉じタグを削除してしまった（`<script src="app.js?v=...">` の状態）。閉じタグがないと後続の`</body>`等がスクリプト内容として飲み込まれ、外部スクリプトが実行されない。

**誤診も記録**: 当初「キャッシュ破損」と誤診した。`transferSize:0`（キャッシュ読込）に引きずられたが、真因はHTMLの構文破壊だった。動的に`createElement('script')`で注入すると動いたため（=コード自体は正常）、切り分けで確定できた。

**再発防止（How to apply）**:
- HTMLの`<script>`/`<link>`等のタグを編集したら、必ず開閉タグの対応を確認する（例: `grep -c '<script' / '</script>'` で一致確認）。
- 「動かない」報告では、まずブラウザで関数/DOMの実体を確認する。関数が全て`undefined`＝スクリプト未実行＝**ロード失敗かHTML構文破壊**を最優先で疑う（キャッシュより先に）。
- キャッシュ説に飛びつく前に、`curl`でライブHTMLの該当タグを直接目視する。

**関連**: GitHub Pagesは`pages-build-deployment`ワークフローでデプロイ。GitHub障害(503)時はデプロイが失敗し得るので、`gh run list`でrun結果(success/failure)を確認し、失敗なら`gh run rerun`で再実行する。反映は`curl -sI`の`last-modified`と`age`で判断（HTMLのCDN TTLは約600秒）。
