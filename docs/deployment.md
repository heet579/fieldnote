# Deployment

Public explorer: **https://fieldnote-torrens.vercel.app**

[About the data](https://fieldnote-torrens.vercel.app/about) · [Daily summaries](https://fieldnote-torrens.vercel.app/daily-observations.csv) · [Source details](https://fieldnote-torrens.vercel.app/source.json)

Vercel project `fieldnote-torrens`, scope `heet-s-projects3`. Only `site/` is uploaded. It contains the explorer, About page, public CSVs/manifests, verification records and a source archive. No local databases, `.env`, login credentials or private posting drafts are deployed.

```powershell
python -m scripts.refresh_report
python -m scripts.verify_real
node scripts/check_report.cjs
python -m scripts.package
python -m scripts.build_site
vercel deploy site --prod --yes --project fieldnote-torrens --scope heet-s-projects3
python -m scripts.verify_deployment
```

Python performs local ETL; the host serves a static snapshot. A new source load requires re-export, checks and redeployment. The public source download is `Fieldnote-Source.zip`. Old case-study and download URLs redirect to their current equivalents.

`portfolio/deployment-verification.json` records the most recent public HTTP checks. `portfolio/browser-verification.json` records desktop/mobile interactions and filtered-CSV verification. Deployment IDs change with updates; the stable public URL remains the same.
