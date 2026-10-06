# ebisu-report

えびす旅館 実績＆受注ペーシング レポート（GitHub Pages で公開・閲覧パスワード付き）

- 公開: https://best1ogawa-hub.github.io/ebisu-report/ （`index.html` = 暗号化済み）
- 更新: Claude のスケジュールタスク「えびす旅館 週次レポート（クラウド）」が毎週月曜に自動生成して push

## 構成

```
tools/build_report.py   レポート生成（集計 → report.html → 暗号化 index.html）
template/head.html      <head> と CSS
template/charts.js      Chart.js の描画・表（D オブジェクトを参照）
template/lock.html      パスワード入力ページ（PBKDF2 + AES-GCM、ブラウザ内で復号）
index.html              公開物（生成物。手で編集しない）
```

## データソース

Google スプレッドシート `ogawa_ebisu_自動更新`（ねっぱん予約通知メールを GAS で 15 分おきに取込）

- `予約一覧` … 予約番号キーの台帳（状態・チェックイン/アウト・泊数・室数・人数・金額・申込日・キャンセル日）
- `実績_履歴` … 2024-01〜2025-12 の宿泊月実績（ねっぱん入込状況表から固定。2026-01 以降は予約一覧から計算）

## 使い方

```
python3 tools/build_report.py \
  --reservations <予約一覧の get_values 結果 JSON> \
  --history      <実績_履歴の get_values 結果 JSON> \
  --asof 2026-10-07 \
  --narrative narrative.json   # 任意: {"note1":..,"insight1":..,"insight2":..,"bk_note":..}（HTML可）
  --out-dir out --password <閲覧パスワード>
```

`--summary-only` を付けると `summary.json`（集計値と自動生成コメント）だけを出す。コメントを書いてから本生成する流れ用。

## 集計定義

`tools/build_report.py` 冒頭の docstring を参照（旧ローカル版・ねっぱん入込状況表と同じ定義）。
