# 外部OSSのマージ済みPR集計

GitHub Actionsが毎日9:17（日本時間）に、noritaka1166 の公開PRを集計します。年度は日本時間の4月1日から翌年3月31日まで。投稿年度を問わず、年度内にマージされたPRを対象とします。

自身所有のリポジトリ・フォークは除外し、他人所有のフォークは含めます。結果はowner → repo → PR番号の昇順です。

## 実行とダウンロード

デフォルトブランチへのマージ後、Actions → Update external OSS merged PRs → Run workflow で手動実行できます。年度開始年（例: 2026）を指定するか、空欄で現在年度を集計します。

実行ページの Artifacts → external-oss-prs から次のファイルをダウンロードできます。

- noritaka1166_external_oss_merged_prs_fy2026.csv
- noritaka1166_external_oss_merged_prs_fy2026_by_repository.csv
- noritaka1166_external_oss_merged_prs_fy2026_report.json

実際の年度番号は実行時の年度に従います。Artifactの保存期間は90日（リポジトリ側の保存期間制限を受けます）。

標準の GITHUB_TOKEN を実行時に利用します。トークンをファイルに記載する必要はありません。

## 任意の自動コミット

初期状態ではCSVをGitへ自動コミットしません。有効化する場合は Settings → Secrets and variables → Actions → Variables に次のRepository variableを追加します。

- 名前: OSS_PRS_COMMIT
- 値: true

結果が変わった場合のみ、generated/配下のCSVをデフォルトブランチにコミットします。書き込み権限はこの設定で動くcommitジョブのみに付与します。ブランチ保護や組織の権限設定によりpushできない場合、commitジョブは失敗しますがArtifactは取得できます。

従来の noritaka1166_external_oss_prs_fy2026.csv や日付付きの既存CSVは変更しません。監査レポートの取得日時だけで毎日コミットが発生しないよう、JSONはコミット対象から外しています。

## 年度とCSV形式

定期実行は日本時間の現在年度を選択し、2027年4月以降はFY2027の別ファイルを生成します。過去年度は手動実行で指定できます。定期実行は過去年度を再取得しません。

主CSVは既存と同じ9列です。

```text
repository,pr_number,title,created_at,state,merged,merged_at,closed_at,url
```

UTF-8 BOM付き、CRLF改行。日時列はUTCのISO 8601表記を維持します。集計CSVはowner・リポジトリ別件数、投稿年度別内訳、フォーク情報を含みます。

## 検索・更新の扱い

月別検索、100件ごとのページ送り、検索件数と取得件数の照合を行います。検索上限1000件や不完全な検索応答は、期間を分割して再取得します。1日まで分割しても完全に取得できない場合、処理を失敗として停止します。API制限・一時エラーには再試行します。

全PRのマージ日時・投稿者・提出先ownerとリポジトリの公開状態・フォーク情報を確認し、検索と検証が完了してから出力します。CSVの生成に失敗した場合、Gitへの自動コミットは実行されません。API待機が15分を超える場合や集計ジョブが60分を超える場合も失敗します。

公開・検索索引登録済みのPRが対象です。削除、非公開化、索引の反映遅延、移管履歴による欠落は保証できません。ownerは実行時点の情報です。

定期実行はGitHub側の混雑で遅延・省略される場合があります。公開リポジトリで60日間活動がない場合は定期実行が無効になるため、必要に応じてActions画面で再度有効にしてください。

## ローカル実行

Python 3.12以上、標準ライブラリのみ。GH_TOKENまたはGITHUB_TOKENを環境変数に設定して実行します。

```bash
python scripts/collect_external_oss_prs.py --author noritaka1166 --fiscal-year 2026 --output-dir generated
```

## 公式資料

- [検索API・上限・不完全な応答](https://docs.github.com/en/rest/search/search)
- [定期実行の仕様](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GITHUB_TOKENと権限](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
