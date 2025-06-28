import os
import requests
from collections import defaultdict

# 設定
GITHUB_TOKEN = os.getenv("GH_TOKEN")
USERNAME = "noritaka1166"
README_PATH = "README.md"
MARKER_START = "<!-- CONTRIBUTIONS:START -->"
MARKER_END = "<!-- CONTRIBUTIONS:END -->"

SEARCH_QUERY = f"is:pr is:merged author:{USERNAME}"

def fetch_all_contributed_repos_via_search():
    repos = set()
    has_next_page = True
    after = None

    while has_next_page:
        query = """
        query ($query: String!, $after: String) {
          search(query: $query, type: ISSUE, first: 100, after: $after) {
            pageInfo {
              endCursor
              hasNextPage
            }
            nodes {
              ... on PullRequest {
                repository {
                  nameWithOwner
                  isFork
                }
              }
            }
          }
        }
        """

        variables = {
            "query": SEARCH_QUERY,
            "after": after
        }

        response = requests.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables},
            headers={"Authorization": f"bearer {GITHUB_TOKEN}"}
        )

        data = response.json()

        if "errors" in data:
            raise Exception(data["errors"])

        for pr in data["data"]["search"]["nodes"]:
            repo = pr["repository"]
            if not repo["isFork"]:
                repos.add(repo["nameWithOwner"])

        page_info = data["data"]["search"]["pageInfo"]
        after = page_info["endCursor"]
        has_next_page = page_info["hasNextPage"]

    return sorted(repos)

def update_readme(repos):
    grouped = defaultdict(list)
    for full_name in repos:
        owner, name = full_name.split("/")
        grouped[owner].append(name)

    new_lines = [MARKER_START]
    for owner in sorted(grouped):
        new_lines.append(f"- **{owner}**")
        for name in sorted(grouped[owner]):
            pr_url = f"https://github.com/{owner}/{name}/pulls?q=is%3Apr+author%3A{USERNAME}"
            new_lines.append(f"  - [{name}]({pr_url})")
    new_lines.append(MARKER_END)
    new_section = "\n".join(new_lines)

    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if MARKER_START in content and MARKER_END in content:
        before = content.split(MARKER_START)[0]
        after = content.split(MARKER_END)[1]
        updated = before + new_section + after
    else:
        updated = content + "\n" + new_section + "\n"

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(updated)

if __name__ == "__main__":
    if not GITHUB_TOKEN:
        raise EnvironmentError("GH_TOKEN is not set in environment variables")
    repos = fetch_all_contributed_repos_via_search()
    update_readme(repos)
