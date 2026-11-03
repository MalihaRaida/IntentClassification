# Hosting the annotation page (GitHub Pages + Google Sheets)

The page is a static site in `docs/`. Labels are saved to a Google Sheet you own,
through a small Google Apps Script web app. Annotators sign in with an access code
you give them; each one only ever loads their own labels.

## 1. Create the Google Sheet backend (about 5 minutes)

1. Create a new Google Sheet, e.g. "Intent annotation labels".
2. **Extensions → Apps Script**. Delete the starter code and paste in
   `annotation_tool/apps_script/Code.gs`. Save.
3. In the function dropdown pick **setup** and click **Run**. Approve the
   permission prompt (it only needs access to this spreadsheet).
   This creates two tabs: **Annotators** and **Labels**.
4. In **Annotators**, replace the two sample rows with your real annotators:
   one row each, column A = access code (make it hard to guess, e.g. `ANN-7KQ2X`),
   column B = name.
5. **Deploy → New deployment** → type **Web app**:
   - Execute as: **Me**
   - Who has access: **Anyone**
   Click **Deploy** and copy the **Web app URL** (ends in `/exec`).
6. Paste that URL into `docs/config.js`:
   ```js
   window.ANNOTATION_API_URL = "https://script.google.com/macros/s/XXXX/exec";
   ```

If you later change `Code.gs`, use **Deploy → Manage deployments → Edit →
Version: New version** so the URL stays the same.

## 2. Publish on GitHub Pages (free)

GitHub Pages is free for public repositories. The page contains only the
public GitHub review comments; access codes and labels stay in your Sheet.

1. Create a new public repository on GitHub, e.g. `intent-annotation`.
2. Push this project (the `.gitignore` keeps `.env`, which holds your GitHub
   token, out of the repo):
   ```bash
   git init
   git add .
   git commit -m "Annotation site"
   git branch -M main
   git remote add origin https://github.com/<you>/intent-annotation.git
   git push -u origin main
   ```
   Pushing only the `docs/` folder is enough if you'd rather keep the rest private.
3. On GitHub: **Settings → Pages → Build and deployment → Source: Deploy from a
   branch**, Branch **main**, folder **/docs**. Save.
4. After a minute the site is live at `https://<you>.github.io/intent-annotation/`.

## 3. Send to annotators

Send each annotator the site link, their own access code, and `AnnotationScheme.pdf`.
Their labels save automatically and they can resume on any device with the same code.

## Results

Open the **Labels** tab: one row per annotator per item with `labels`
(semicolon-separated codes), `confidence`, `rationale`, `flag`, `status`
(`done` / `partial`) and timestamps. **File → Download → CSV** to analyse it.

## Rebuilding after data changes

```bash
python annotation_tool/build_annotation_page.py
```
This regenerates `docs/index.html` from `annotation_tool/site_template.html` and
leaves `docs/config.js` alone. Commit and push to update the live site.
