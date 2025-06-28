import os
import requests

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
          repository {
            nameWithOwner
            isFork
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
            repo = node["repository"]
            if not repo["isFork"]:  # 除外：フォーク
                repos.add(repo["nameWithOwner"])

        if not pr_contribs["pageInfo"]["hasNextPage"]:
            break
        after = pr_contribs["pageInfo"]["endCursor"]

    return sorted(repos)

def update_readme(repos):
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    before, _, after = content.partition(MARKER)
    new_content = f"{before}{MARKER}\n" + "\n".join(f"- [{r}](https://github.com/{r})" for r in repos) + "\n"

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content + after)

if __name__ == "__main__":
    repos = fetch_all_contributed_repos()
    update_readme(repos)
