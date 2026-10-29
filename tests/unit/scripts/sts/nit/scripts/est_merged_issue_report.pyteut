"""GraphQL read audit failures must not become empty complete reports."""

import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

path = Path(__file__).resolve().parents[3] / "scripts/report-merged-issue-references.py"
spec = importlib.util.spec_from_file_location("reference_report", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def connection(nodes, more=False, cursor=None):
    return {"nodes": nodes, "pageInfo": {"hasNextPage": more, "endCursor": cursor}}


def pr(state="MERGED", draft=False):
    return {
        "number": 3,
        "state": state,
        "isDraft": draft,
        "mergedAt": "2026-10-01T00:00:00Z" if state == "MERGED" else None,
        "url": "https://github.com/Q00/ouroboros/pull/3",
        "repository": {"nameWithOwner": "Q00/ouroboros"},
    }


class Fake:
    def __init__(self, pull=None):
        self.pull = pull or pr()

    def query(self, query, variables):
        if query == m.ISSUES_QUERY:
            return {"repository": {"issues": connection([{"number": 1}])}}
        if query == m.REFS_QUERY:
            node = {
                "__typename": "CrossReferencedEvent",
                "willCloseTarget": False,
                "source": {"__typename": "PullRequest", **self.pull},
            }
            field, nodes = "timelineItems", [node]
        else:
            field, nodes = "closedByPullRequestsReferences", [self.pull]
        return {"repository": {"issue": {"state": "OPEN", field: connection(nodes)}}}


def test_candidate_includes_plain_and_closing_and_repeated_reads_equal():
    client = Fake()
    result = m.report(client, "Q00/ouroboros")
    assert result == m.report(client, "Q00/ouroboros")
    assert result["candidates"][0]["references"][0]["reference_kinds"] == ["closing", "plain"]


@pytest.mark.parametrize(
    "state,draft", [("OPEN", False), ("CLOSED", False), ("OPEN", True), ("MERGED", True)]
)
def test_nonmerged_or_draft_blocks(state, draft):
    assert not m.report(Fake(pr(state, draft)), "Q00/ouroboros")["candidates"]


def test_no_refs_and_foreign_repo_absent():
    pull = pr()
    pull["repository"]["nameWithOwner"] = "other/repo"
    assert not m.report(Fake(pull), "Q00/ouroboros")["candidates"]


def test_missing_repository_indeterminate():
    client = Fake()
    client.query = lambda _query, _variables: {"repository": None}
    with pytest.raises(m.IndeterminateAudit):
        m.report(client, "Q00/ouroboros")


def test_pagination_all_three_connections():
    class Pages(Fake):
        def query(self, query, variables):
            result = super().query(query, variables)
            parent = (
                result["repository"] if query == m.ISSUES_QUERY else result["repository"]["issue"]
            )
            field = (
                "issues"
                if query == m.ISSUES_QUERY
                else (
                    "timelineItems" if query == m.REFS_QUERY else "closedByPullRequestsReferences"
                )
            )
            if variables["after"] is None:
                parent[field] = connection([], True, "cursor1")
            return result

    assert len(m.report(Pages(), "Q00/ouroboros")["candidates"]) == 1


def test_repeated_cursor_indeterminate():
    class Bad(Fake):
        def query(self, query, variables):
            return {"repository": {"issues": connection([], True, "same")}}

    with pytest.raises(m.IndeterminateAudit):
        m.report(Bad(), "Q00/ouroboros")


def test_query_retry_timeout_and_no_mutation():
    calls = []

    def opener(request, timeout):
        assert timeout == 30
        payload = json.loads(request.data)
        assert payload["query"].startswith("query ")
        calls.append(request)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 503, "busy", {}, None)
        return io.BytesIO(b'{"data":{"repository":{}}}')

    client = m.GitHubReads("not-a-real-token", opener, lambda _seconds: None)
    assert client.query(m.ISSUES_QUERY, {}) == {"repository": {}}
    assert len(calls) == 2
    with pytest.raises(m.IndeterminateAudit):
        client.query("mutation X {}", {})


def test_graphql_errors_and_missing_token_not_complete():
    def opener(_request, timeout):
        assert timeout == 30
        return io.BytesIO(b'{"data":{"repository":{}},"errors":[{"message":"redacted"}]}')

    with pytest.raises(m.IndeterminateAudit):
        m.GitHubReads("not-real", opener).query(m.ISSUES_QUERY, {})
    with pytest.raises(m.IndeterminateAudit):
        m.GitHubReads(None).query(m.ISSUES_QUERY, {})
