import os
import requests
from collections import defaultdict

GITHUB_TOKEN = os.getenv("GH_TOKEN")
USERNAME = "noritaka1166"
README_PATH = "README.md"
MARKER_START = "<!-- CONTRIBUTIONS:START -->"
MARKER_END = "<!-- CONTRIBUTIONS:END -->"

QUERY = """
query($username: String!, $after: String) {
  user(login: $username) {
    contributionsCollection {
      pullRequestContributions(first: 100, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          pullRequest {
            merged
            repository {
              nameWithOwner
              isFork
            }
          }
        }
      }
    }
  }
}
"""

def fetch_all_contributed_repos():
    repos = set()
    after = None

    while True:
        variables = {"username": USERNAME, "after": after}
        response = requests.post(
            "https://api.github.com/graphql",
            json={"query": QUERY, "variables": variables},
            headers={"Authorization": f"bearer {GITHUB_TOKEN}"}
        )

        data = response.json()

        if "errors" in data:
            raise Exception(data["errors"])

        pr_contribs = data["data"]["user"]["contributionsCollection"]["pullRequestContributions"]

        for node in pr_contribs["nodes"]:
            pr = node.get("pullRequest")
            if pr and pr.get("merged"):
                repo = pr.get("repository")
                if repo and not repo.get("isFork", False):
                    repos.add(repo["nameWithOwner"])

        if not pr_contribs["pageInfo"]["hasNextPage"]:
            break
        after = pr_contribs["pageInfo"]["endCursor"]

    return sorted(repos)

def update_readme(repos):
    grouped = defaultdict(list)
    for full_name in repos:
        owner, name = full_name.split("/")
        grouped[owner].append(name)

    # 構築する新しいセクション
    new_lines = [MARKER_START]
    for owner in sorted(grouped):
        new_lines.append(f"- **{owner}**")
        for name in sorted(grouped[owner]):
            pr_url = f"https://github.com/{owner}/{name}/pulls?q=is%3Apr+author%3A{USERNAME}"
            new_lines.append(f"  - [{name}]({pr_url})")
    new_lines.append(MARKER_END)
    new_section = "\n".join(new_lines)

    # README の既存内容を読み込み
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # マーカー間の既存セクションを置換
    if MARKER_START in content and MARKER_END in content:
        before = content.split(MARKER_START)[0]
        after = content.split(MARKER_END)[1]
        updated = before + new_section + after
    else:
        # マーカーが存在しない場合は末尾に追記
        updated = content + "\n" + new_section + "\n"

    # 書き戻し
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(updated)

if __name__ == "__main__":
    if not GITHUB_TOKEN:
        raise EnvironmentError("GH_TOKEN is not set in environment variables")
    repos = fetch_all_contributed_repos()
    update_readme(repos)
