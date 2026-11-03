"""
Extract 300 review comments from ronantakizawa/github-codereview (train split).

- Comments are drawn from many different repositories.
- Each selected repository contributes a random number of comments
  (between MIN_PER_REPO and MAX_PER_REPO).
- Every comment is at least MIN_COMMENT_LEN characters long (after stripping whitespace).
- For each comment, the PR description and the previous / next comment in the
  same review thread are fetched from the GitHub API (cached in GITHUB_CACHE_DIR).
  Set the GITHUB_TOKEN environment variable; without it GitHub allows only
  60 requests per hour.
- Output: review_comment_collection.csv
"""

import json
import os
import random
import time
from pathlib import Path
from dotenv import load_dotenv
 
import pandas as pd
import requests
from datasets import load_dataset

TOTAL_COMMENTS = 300
MIN_COMMENT_LEN = 15
MIN_PER_REPO = 1
MAX_PER_REPO = 5
SEED = 42
OUTPUT_CSV = "review_comment_collection.csv"
GITHUB_CACHE_DIR = Path("github_cache")
GITHUB_API = "https://api.github.com"

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
KEEP_COLUMNS = [
    "repo_name",
    "pr_number",
    "pr_title",
    "file_path",
    "language",
    "reviewer_comment",
    "diff_context",
    "comment_type",
    "comment_length",
]

random.seed(SEED)

ds = load_dataset("ronantakizawa/github-codereview")["train"]
df = ds.select_columns(KEEP_COLUMNS).to_pandas()

# Keep only comments that are at least MIN_COMMENT_LEN characters long
df["reviewer_comment"] = df["reviewer_comment"].fillna("").str.strip()
df = df[df["reviewer_comment"].str.len() >= MIN_COMMENT_LEN]
df = df.drop_duplicates(subset=["repo_name", "reviewer_comment"])

# Visit repositories in random order, taking a random count from each
groups = {repo: g for repo, g in df.groupby("repo_name")}
repos = list(groups)
random.shuffle(repos)

samples = []
collected = 0
for repo in repos:
    if collected >= TOTAL_COMMENTS:
        break
    group = groups[repo]
    k = random.randint(MIN_PER_REPO, MAX_PER_REPO)
    k = min(k, len(group), TOTAL_COMMENTS - collected)
    samples.append(group.sample(n=k, random_state=random.randint(0, 2**31 - 1)))
    collected += k

result = pd.concat(samples, ignore_index=True)
result["comment_length"] = result["reviewer_comment"].str.len()
result.insert(
    result.columns.get_loc("pr_number") + 1,
    "pr_url",
    "https://github.com/" + result["repo_name"] + "/pull/" + result["pr_number"].astype(str),
)


session = requests.Session()
session.headers["Accept"] = "application/vnd.github+json"
if os.environ.get("GITHUB_TOKEN"):
    session.headers["Authorization"] = f"Bearer {os.environ.get("GITHUB_TOKEN")}"
else:
    print("Warning: GITHUB_TOKEN is not set; GitHub limits you to 60 requests/hour.")


def github_get(url, params=None):
    """GET a GitHub API URL, waiting out rate limits. Returns None on 404/410."""
    while True:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
            wait = max(int(resp.headers.get("X-RateLimit-Reset", time.time() + 60)) - time.time(), 0) + 5
            print(f"Rate limited; sleeping {wait:.0f}s")
            time.sleep(wait)
            continue
        if resp.status_code in (404, 410, 451):
            return None
        resp.raise_for_status()
        return resp


def fetch_pr(repo, pr_number):
    """PR description and all inline review comments, cached on disk."""
    cache_file = GITHUB_CACHE_DIR / f"{repo.replace('/', '__')}__{pr_number}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    pr = github_get(f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}")
    data = {"description": "", "comments": []}
    if pr is not None:
        data["description"] = pr.json().get("body") or ""
        url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/comments"
        params = {"per_page": 100}
        while url:
            resp = github_get(url, params)
            if resp is None:
                break
            data["comments"].extend(
                {
                    "id": c["id"],
                    "in_reply_to_id": c.get("in_reply_to_id"),
                    "path": c.get("path"),
                    "user": (c.get("user") or {}).get("login"),
                    "created_at": c["created_at"],
                    "body": c.get("body") or "",
                }
                for c in resp.json()
            )
            url = resp.links.get("next", {}).get("url")
            params = None

    GITHUB_CACHE_DIR.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def normalize(text):
    return " ".join(text.split())


def thread_context(comments, comment_text, file_path):
    """Find the comment in its review thread and return its neighbours."""
    target = normalize(comment_text)
    candidates = [c for c in comments if normalize(c["body"]) == target]
    if not candidates:
        candidates = [c for c in comments if normalize(c["body"])[:100] == target[:100]]
    if not candidates:
        return None
    match = next((c for c in candidates if c["path"] == file_path), candidates[0])

    root_id = match["in_reply_to_id"] or match["id"]
    thread = sorted(
        (c for c in comments if c["id"] == root_id or c["in_reply_to_id"] == root_id),
        key=lambda c: c["created_at"],
    )
    idx = next(i for i, c in enumerate(thread) if c["id"] == match["id"])
    nxt = thread[idx + 1] if idx + 1 < len(thread) else None

    # Previous comment is PR-wide: the review comment posted just before this
    # one in any thread (dataset comments usually start their own thread).
    pr_order = sorted(comments, key=lambda c: (c["created_at"], c["id"]))
    pr_idx = next(i for i, c in enumerate(pr_order) if c["id"] == match["id"])
    prev = pr_order[pr_idx - 1] if pr_idx > 0 else None
    return {
        "previous_comment": prev["body"] if prev else "",
        "previous_comment_author": prev["user"] if prev else "",
        "after_comment": nxt["body"] if nxt else "",
        "after_comment_author": nxt["user"] if nxt else "",
    }


pr_keys = result[["repo_name", "pr_number"]].drop_duplicates().itertuples(index=False)
pr_data = {}
for i, (repo, pr_number) in enumerate(pr_keys, 1):
    print(f"Fetching PR {i}: {repo}#{pr_number}")
    pr_data[(repo, pr_number)] = fetch_pr(repo, pr_number)

empty_context = {
    "previous_comment": "",
    "previous_comment_author": "",
    "after_comment": "",
    "after_comment_author": "",
}
descriptions, contexts, matched = [], [], []
for row in result.itertuples(index=False):
    data = pr_data[(row.repo_name, row.pr_number)]
    descriptions.append(data["description"])
    ctx = thread_context(data["comments"], row.reviewer_comment, row.file_path)
    matched.append(ctx is not None)
    contexts.append(ctx or empty_context)

result.insert(result.columns.get_loc("pr_title") + 1, "pr_description", descriptions)
context_df = pd.DataFrame(contexts)
comment_pos = result.columns.get_loc("reviewer_comment")
for offset, col in enumerate(["previous_comment", "previous_comment_author"]):
    result.insert(comment_pos + offset, col, context_df[col])
after_pos = result.columns.get_loc("reviewer_comment") + 1
for offset, col in enumerate(["after_comment", "after_comment_author"]):
    result.insert(after_pos + offset, col, context_df[col])
result["found_on_github"] = matched

result = result.sample(frac=1, random_state=SEED).reset_index(drop=True)
result.insert(0, "id", range(1, len(result) + 1))

result.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

print(f"Saved {len(result)} comments to {OUTPUT_CSV}")
print(f"Repositories used: {result['repo_name'].nunique()}")
print(f"Shortest comment length: {result['comment_length'].min()}")
print(f"Comments found on GitHub: {result['found_on_github'].sum()}")
print(f"With previous comment: {(result['previous_comment'] != '').sum()}")
print(f"With after comment: {(result['after_comment'] != '').sum()}")
print(f"With PR description: {(result['pr_description'] != '').sum()}")
print("Comments per repository:")
print(result["repo_name"].value_counts().describe())
