#!/usr/bin/env python3
"""Explicit read-only GitHub reference audit (#1861), using GraphQL query only.

Requires GH_TOKEN with repository read access. Never mutates GitHub. Historical
visible references are evidence, not a recommendation to close an issue.
"""

import argparse
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class IndeterminateAudit(RuntimeError):
    """The audit could not obtain complete evidence."""


class GitHubReads:
    def __init__(self, token, opener=urlopen, sleep=time.sleep):
        self.token, self.opener, self.sleep = token, opener, sleep

    def query(self, query, variables):
        if not self.token:
            raise IndeterminateAudit("GH_TOKEN required for GitHub GraphQL read queries")
        if not query.lstrip().startswith("query "):
            raise IndeterminateAudit("Only explicit read queries allowed")
        request = Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": query, "variables": variables}).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        for attempt in range(3):
            try:
                with self.opener(request, timeout=30) as response:
                    payload = json.load(response)
                if (
                    not isinstance(payload, dict)
                    or payload.get("errors")
                    or not payload.get("data")
                ):
                    raise IndeterminateAudit("GraphQL returned errors or incomplete data")
                return payload["data"]
            except HTTPError as error:
                if attempt < 2 and (error.code == 429 or error.code >= 500):
                    self.sleep(2**attempt)
                    continue
                raise IndeterminateAudit(f"GitHub read failed: HTTP {error.code}") from error
            except (URLError, OSError, ValueError) as error:
                raise IndeterminateAudit(f"GitHub read failed: {type(error).__name__}") from error
        raise IndeterminateAudit("Retry budget exhausted")


PR_FIELDS = "number state isDraft mergedAt url repository { nameWithOwner }"
ISSUES_QUERY = """query Issues($owner:String!,$name:String!,$after:String) {
 repository(owner:$owner,name:$name) {
  issues(states:OPEN,first:100,after:$after,orderBy:{field:CREATED_AT,direction:ASC}) {
   nodes { number title url } pageInfo { hasNextPage endCursor }
  }
 }
}"""
REFS_QUERY = """query Refs($owner:String!,$name:String!,$number:Int!,$after:String) {
 repository(owner:$owner,name:$name) { issue(number:$number) {
  state timelineItems(first:100,after:$after,itemTypes:[CROSS_REFERENCED_EVENT,CONNECTED_EVENT]) {
   nodes {
    __typename
    ... on CrossReferencedEvent { willCloseTarget source { __typename ... on PullRequest { __PR_FIELDS__ } } }
    ... on ConnectedEvent { source { __typename ... on PullRequest { __PR_FIELDS__ } } }
   } pageInfo { hasNextPage endCursor }
  }
 } }
}""".replace("__PR_FIELDS__", PR_FIELDS)
CLOSING_QUERY = """query Closing($owner:String!,$name:String!,$number:Int!,$after:String) {
 repository(owner:$owner,name:$name) { issue(number:$number) {
  state closedByPullRequestsReferences(first:100,after:$after,includeClosedPrs:true) {
   nodes { __PR_FIELDS__ } pageInfo { hasNextPage endCursor }
  }
 } }
}""".replace("__PR_FIELDS__", PR_FIELDS)


def paginated(client, query, variables, field):
    after = None
    seen = set()
    while True:
        data = client.query(query, {**variables, "after": after})
        repository = data.get("repository")
        if not isinstance(repository, dict):
            raise IndeterminateAudit("Repository unavailable")
        parent = repository if field == "issues" else repository.get("issue")
        if not isinstance(parent, dict):
            raise IndeterminateAudit("Issue missing or transferred")
        if field != "issues" and parent.get("state") != "OPEN":
            raise IndeterminateAudit("Issue changed state during audit")
        connection = parent.get(field)
        if not isinstance(connection, dict) or not isinstance(connection.get("nodes"), list):
            raise IndeterminateAudit("Missing paginated reference evidence")
        yield from connection["nodes"]
        info = connection.get("pageInfo")
        if not isinstance(info, dict) or type(info.get("hasNextPage")) is not bool:
            raise IndeterminateAudit("Missing pagination state")
        if not info["hasNextPage"]:
            return
        after = info.get("endCursor")
        if not isinstance(after, str) or not after or after in seen:
            raise IndeterminateAudit("Invalid or repeated pagination cursor")
        seen.add(after)


def report(client, repository):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise IndeterminateAudit("Expected owner/repository")
    owner, name = repository.split("/")
    variables = {"owner": owner, "name": name}
    candidates = []
    seen_issues = set()
    for issue in paginated(client, ISSUES_QUERY, variables, "issues"):
        if not isinstance(issue, dict) or type(issue.get("number")) is not int:
            raise IndeterminateAudit("Malformed issue record")
        number = issue["number"]
        if number in seen_issues:
            raise IndeterminateAudit("Duplicate issue during pagination")
        seen_issues.add(number)
        refs = {}

        def add(pr, kind):
            if not isinstance(pr, dict):
                raise IndeterminateAudit("Missing reference source")
            repo = pr.get("repository")
            if not isinstance(repo, dict) or not isinstance(repo.get("nameWithOwner"), str):
                raise IndeterminateAudit("Reference repository missing or transferred")
            if repo["nameWithOwner"].lower() != repository.lower():
                return
            pr_number = pr.get("number")
            if type(pr_number) is not int or pr.get("state") not in {"OPEN", "CLOSED", "MERGED"}:
                raise IndeterminateAudit("Malformed PR evidence")
            entry = refs.setdefault(pr_number, {"pr": pr, "kinds": set()})
            if entry["pr"] != pr:
                raise IndeterminateAudit("PR changed during reference reads")
            entry["kinds"].add(kind)

        scoped = {**variables, "number": number}
        for event in paginated(client, REFS_QUERY, scoped, "timelineItems"):
            if not isinstance(event, dict) or not isinstance(event.get("source"), dict):
                raise IndeterminateAudit("Missing timeline source")
            source = event["source"]
            if source.get("__typename") == "Issue":
                continue
            if source.get("__typename") != "PullRequest":
                raise IndeterminateAudit("Unavailable reference source type")
            pr = {key: value for key, value in source.items() if key != "__typename"}
            kind = "closing" if event.get("willCloseTarget") is True else "plain"
            add(pr, kind if event.get("__typename") == "CrossReferencedEvent" else "connected")
        for pr in paginated(client, CLOSING_QUERY, scoped, "closedByPullRequestsReferences"):
            add(pr, "closing")
        if refs and all(
            x["pr"]["state"] == "MERGED"
            and x["pr"].get("mergedAt")
            and x["pr"].get("isDraft") is False
            for x in refs.values()
        ):
            candidates.append(
                {
                    **issue,
                    "references": [
                        {**x["pr"], "reference_kinds": sorted(x["kinds"])}
                        for _, x in sorted(refs.items())
                    ],
                }
            )
    return {
        "repository": repository,
        "status": "complete",
        "candidates": candidates,
        "notice": "Visible direct references are human-review evidence only, not issue completion. "
        "Read over an interval, not an atomic snapshot. No changes made.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Q00/ouroboros")
    args = parser.parse_args()
    try:
        result = report(GitHubReads(os.getenv("GH_TOKEN")), args.repo)
    except IndeterminateAudit as error:
        print(json.dumps({"status": "indeterminate", "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
