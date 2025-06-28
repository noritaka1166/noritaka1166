import os
import requests
from collections import defaultdict

GITHUB_TOKEN = os.getenv("GH_TOKEN")
USERNAME = "noritaka1166"
README_PATH = "README.md"
MARKER = "<!-- CONTRIBUTIONS:START -->"

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
            if pr:
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

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    before, _, after = content.partition(MARKER)

    lines = [f"{MARKER}"]
    for owner in sorted(grouped):
        lines.append(f"- **{owner}**")
        for name in sorted(grouped[owner]):
            lines.append(f"  - [{name}](https://github.com/{owner}/{name})")

    new_content = before + "\n".join(lines) + "\n" + after

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

if __name__ == "__main__":
    if not GITHUB_TOKEN:
        raise EnvironmentError("GH_TOKEN is not set in environment variables")
    repos = fetch_all_contributed_repos()
    update_readme(repos)
