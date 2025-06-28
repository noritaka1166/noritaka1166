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

        pr_contribs = data["data"]["user"]["contributionsCollection"]["pullR]()_
