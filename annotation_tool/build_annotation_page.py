"""
Build the annotation pages: embed review_comment_collection.csv into the templates.

Only the context annotators need is embedded. The dataset's own comment_type
column is left out so it cannot bias the labels.

Outputs:
  docs/index.html                 static site for GitHub Pages (labels go to a Google Sheet)
  docs/config.js                  created once; holds the Apps Script web app URL
  annotation_tool/annotate.html   claude.ai artifact version
"""

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parent
CSV = ROOT / "review_comment_collection.csv"
SITE_DIR = ROOT / "docs"
TARGETS = [
    (HERE / "site_template.html", SITE_DIR / "index.html"),
    (HERE / "template.html", HERE / "annotate.html"),
]
CONFIG_JS = SITE_DIR / "config.js"
CONFIG_TEMPLATE = """
window.ANNOTATION_API_URL = "";
"""

FIELDS = [
    "id",
    "repo_name",
    "pr_number",
    "pr_url",
    "pr_title",
    "pr_description",
    "file_path",
    "language",
    "previous_comment",
    "previous_comment_author",
    "reviewer_comment",
    "after_comment",
    "after_comment_author",
    "diff_context",
]

df = pd.read_csv(CSV, keep_default_na=False)[FIELDS].sort_values("id")
items = df.to_dict(orient="records")

# Escape "<" so no embedded text can close the <script> tag early, and keep
# replacement characters already present in the source data as JSON escapes.
payload = (
    json.dumps(items, ensure_ascii=False)
    .replace("<", "\\u003c")
    .replace("�", "\\ufffd")
)

SITE_DIR.mkdir(exist_ok=True)
for template, output in TARGETS:
    html = template.read_text(encoding="utf-8").replace("/*__ITEMS__*/", payload)
    output.write_text(html, encoding="utf-8")
    print(f"Wrote {output} with {len(items)} items ({output.stat().st_size / 1024:.0f} KB)")

if not CONFIG_JS.exists():
    CONFIG_JS.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    print(f"Wrote {CONFIG_JS}; set the web app URL in it")
