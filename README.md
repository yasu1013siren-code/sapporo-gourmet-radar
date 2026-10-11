# SAPPORO GOURMET RADAR

グルメ系インフルエンサーの取材・投稿先を探す独立サービス。
既存の飲食店向け来店予測・イベント集計サービスとはリポジトリ・公開先・収集出力を分離します。

## 公開する手順
1. GitHubで新しい公開リポジトリ `sapporo-gourmet-radar` を作成します。
2. ZIPを解凍し、全ファイルをリポジトリ直下へアップロードします。`.github/workflows/gourmet-daily.yml`も必須です。ブラウザのアップロードで隠しフォルダが選択できない場合、GitHubのAdd file→Create new fileで同じパスを入力し、YAMLの内容を貼り付けます。
3. Settings→Pages→Build and deployment→Sourceを `GitHub Actions` に設定します。
4. Actions→Gourmet Radar daily update→Run workflowを実行します。緑の成功表示とPagesの公開URLを確認してください。

毎日07:00日本時間に収集します。GitHubの混雑により開始時刻は遅れる場合があります。
公開ページは `public/index.html` で、初回収集後は `public/news.json` が更新されます。
通常は追加のAPIキー不要。課金・会員認証は未実装で、月額500円の料金表示のみです。

## 収集工程
公式施設・主催者と地域メディアの一覧→候補URL→詳細→飲食/所在地/実施日を検証→住所・種別・日付で重複除去→前回データへ差分保存→公開。
記事公開日を開催日に流用しません。日付や店名が曖昧な候補は `unconfirmed.json` に保存します。
画面は前後1暦月に絞り、閉店は本日以降のみ。イベントは期間が重なるものも表示します。
取得失敗で既存情報は削除しません。失敗情報源・受理件数は `collection-report.json` で確認できます。
初回の公開前にActionsの実行結果を確認してください。この配布時点ではネットワーク収集を実行できていません。

## ローカル確認
`python -m pip install -r requirements.txt`
`python -m unittest discover -s tests`
`python collector.py`
`python -m http.server 8000 --directory public`
