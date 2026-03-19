"""
Unit tests for the Enrichr gene-set enrichment tool.

Run with:
    pip install pytest httpx pytest-cov
    python -m pytest tests/test_enrichr_tool.py -v
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from toolserver.tools.enrichr_pathway import (
    _normalize_enrichr_payload,
    _row_to_item,
    _run,
    _sort_and_top,
    _validate,
)

# ===========================================================================
# Helpers / fixtures
# ===========================================================================

def _make_row(
    rank=1,
    term="Pathway A",
    p_value=0.01,
    z_score=-1.5,
    combined_score=10.0,
    overlap_genes=None,
    adj_p_value=0.05,
    old_p_value=0.01,
    old_adj_p_value=0.05,
) -> List[Any]:
    return [
        rank,
        term,
        p_value,
        z_score,
        combined_score,
        overlap_genes if overlap_genes is not None else ["GENE1", "GENE2"],
        adj_p_value,
        old_p_value,
        old_adj_p_value,
    ]


def _make_items(n: int) -> List[Dict[str, Any]]:
    """Create n items with predictably increasing p-values."""
    return [
        {
            "rank": i + 1,
            "term": f"Term {i}",
            "p_value": (i + 1) * 0.01,
            "z_score": -float(i),
            "combined_score": float(100 - i * 10),
            "overlap_genes": ["G1", "G2"],
            "adj_p_value": (i + 1) * 0.05,
            "old_p_value": None,
            "old_adj_p_value": None,
        }
        for i in range(n)
    ]


# ===========================================================================
# _validate
# ===========================================================================

class TestValidate:

    # --- genes ---

    def test_valid_minimal(self):
        result = _validate({"genes": ["TP53", "BRCA1"]}, {})
        assert result["ok"] is True
        assert result["errors"] == []

    def test_genes_missing(self):
        result = _validate({}, {})
        assert result["ok"] is False
        fields = [e["field"] for e in result["errors"]]
        assert "genes" in fields

    def test_genes_empty_list(self):
        result = _validate({"genes": []}, {})
        assert result["ok"] is False

    def test_genes_not_a_list(self):
        result = _validate({"genes": "TP53"}, {})
        assert result["ok"] is False

    def test_genes_list_with_blank_string(self):
        result = _validate({"genes": ["TP53", "  "]}, {})
        assert result["ok"] is False

    def test_genes_non_string_elements(self):
        result = _validate({"genes": [123, "BRCA1"]}, {})
        assert result["ok"] is False

    # --- libraries ---

    def test_libraries_none_allowed(self):
        result = _validate({"genes": ["TP53"], "libraries": None}, {})
        assert result["ok"] is True

    def test_libraries_valid(self):
        result = _validate({"genes": ["TP53"], "libraries": ["KEGG_2021_Human"]}, {})
        assert result["ok"] is True

    def test_libraries_empty_list(self):
        result = _validate({"genes": ["TP53"], "libraries": []}, {})
        assert result["ok"] is False

    def test_libraries_not_a_list(self):
        result = _validate({"genes": ["TP53"], "libraries": "KEGG_2021_Human"}, {})
        assert result["ok"] is False

    def test_libraries_blank_element(self):
        result = _validate({"genes": ["TP53"], "libraries": ["  "]}, {})
        assert result["ok"] is False

    # --- top_n ---

    def test_top_n_valid(self):
        result = _validate({"genes": ["TP53"], "top_n": 10}, {})
        assert result["ok"] is True

    def test_top_n_as_string_integer(self):
        result = _validate({"genes": ["TP53"], "top_n": "50"}, {})
        assert result["ok"] is True

    def test_top_n_zero(self):
        result = _validate({"genes": ["TP53"], "top_n": 0}, {})
        assert result["ok"] is False

    def test_top_n_above_500(self):
        result = _validate({"genes": ["TP53"], "top_n": 501}, {})
        assert result["ok"] is False

    def test_top_n_boundary_1(self):
        result = _validate({"genes": ["TP53"], "top_n": 1}, {})
        assert result["ok"] is True

    def test_top_n_boundary_500(self):
        result = _validate({"genes": ["TP53"], "top_n": 500}, {})
        assert result["ok"] is True

    def test_top_n_non_numeric(self):
        result = _validate({"genes": ["TP53"], "top_n": "abc"}, {})
        assert result["ok"] is False

    # --- sort_by ---

    def test_sort_by_adj_p_value(self):
        result = _validate({"genes": ["TP53"], "sort_by": "adj_p_value"}, {})
        assert result["ok"] is True

    def test_sort_by_p_value(self):
        result = _validate({"genes": ["TP53"], "sort_by": "p_value"}, {})
        assert result["ok"] is True

    def test_sort_by_combined_score(self):
        result = _validate({"genes": ["TP53"], "sort_by": "combined_score"}, {})
        assert result["ok"] is True

    def test_sort_by_invalid(self):
        result = _validate({"genes": ["TP53"], "sort_by": "fdr"}, {})
        assert result["ok"] is False

    # --- warnings list always present ---

    def test_warnings_always_present(self):
        result = _validate({"genes": ["TP53"]}, {})
        assert "warnings" in result

    # --- multiple errors ---

    def test_multiple_errors_accumulated(self):
        result = _validate({"genes": [], "top_n": -1, "sort_by": "bad"}, {})
        fields = [e["field"] for e in result["errors"]]
        assert "genes" in fields
        assert "top_n" in fields
        assert "sort_by" in fields


# ===========================================================================
# _row_to_item
# ===========================================================================

class TestRowToItem:

    def test_full_row_parsed(self):
        row = _make_row()
        item = _row_to_item(row)
        assert item is not None
        assert item["rank"] == 1
        assert item["term"] == "Pathway A"
        assert item["p_value"] == pytest.approx(0.01)
        assert item["z_score"] == pytest.approx(-1.5)
        assert item["combined_score"] == pytest.approx(10.0)
        assert item["overlap_genes"] == ["GENE1", "GENE2"]
        assert item["adj_p_value"] == pytest.approx(0.05)
        assert item["old_p_value"] == pytest.approx(0.01)
        assert item["old_adj_p_value"] == pytest.approx(0.05)

    def test_short_row_7_elements(self):
        row = _make_row()[:7]
        item = _row_to_item(row)
        assert item is not None
        assert item["old_p_value"] is None
        assert item["old_adj_p_value"] is None

    def test_row_too_short_returns_none(self):
        assert _row_to_item([1, "Term", 0.01]) is None

    def test_non_list_returns_none(self):
        assert _row_to_item("not a list") is None  # type: ignore
        assert _row_to_item(None) is None  # type: ignore

    def test_blank_term_returns_none(self):
        row = _make_row(term="  ")
        assert _row_to_item(row) is None

    def test_empty_term_returns_none(self):
        row = _make_row(term="")
        assert _row_to_item(row) is None

    def test_non_numeric_p_value_becomes_none(self):
        row = _make_row()
        row[2] = "not_a_float"
        item = _row_to_item(row)
        assert item is not None
        assert item["p_value"] is None

    def test_non_numeric_rank_becomes_none(self):
        row = _make_row()
        row[0] = "one"
        item = _row_to_item(row)
        assert item is not None
        assert item["rank"] is None

    def test_overlap_genes_non_list_becomes_empty(self):
        row = _make_row()
        row[5] = "GENE1;GENE2"  # string instead of list
        item = _row_to_item(row)
        assert item is not None
        assert item["overlap_genes"] == []

    def test_overlap_genes_list_preserved(self):
        row = _make_row(overlap_genes=["A", "B", "C"])
        item = _row_to_item(row)
        assert item["overlap_genes"] == ["A", "B", "C"]


# ===========================================================================
# _normalize_enrichr_payload
# ===========================================================================

class TestNormalizeEnrichrPayload:

    def test_basic_normalization(self):
        lib = "WikiPathways_2024_Human"
        payload = {lib: [_make_row(), _make_row(rank=2, term="Pathway B", adj_p_value=0.1)]}
        result = _normalize_enrichr_payload(payload, lib)
        assert result["library"] == lib
        assert result["n_terms"] == 2
        assert len(result["items"]) == 2
        assert "columns" in result

    def test_empty_library_key(self):
        lib = "WikiPathways_2024_Human"
        result = _normalize_enrichr_payload({lib: []}, lib)
        assert result["n_terms"] == 0
        assert result["items"] == []

    def test_missing_library_key(self):
        result = _normalize_enrichr_payload({}, "SomeLib")
        assert result["n_terms"] == 0

    def test_invalid_rows_skipped(self):
        lib = "WikiPathways_2024_Human"
        payload = {lib: [[1, "", 0.01, -1, 10, [], 0.05], _make_row()]}
        result = _normalize_enrichr_payload(payload, lib)
        assert result["n_terms"] == 1

    def test_columns_list(self):
        lib = "Reactome_2022"
        result = _normalize_enrichr_payload({lib: [_make_row()]}, lib)
        expected_cols = [
            "rank", "term", "p_value", "z_score", "combined_score",
            "overlap_genes", "adj_p_value", "old_p_value", "old_adj_p_value",
        ]
        assert result["columns"] == expected_cols

    def test_none_payload_handled(self):
        result = _normalize_enrichr_payload(None, "SomeLib")  # type: ignore
        assert result["n_terms"] == 0


# ===========================================================================
# _sort_and_top
# ===========================================================================

class TestSortAndTop:

    def test_sort_by_adj_p_value_ascending(self):
        items = _make_items(5)
        result = _sort_and_top(items, sort_by="adj_p_value", top_n=5)
        vals = [r["adj_p_value"] for r in result]
        assert vals == sorted(vals)

    def test_sort_by_p_value_ascending(self):
        items = _make_items(5)
        result = _sort_and_top(items, sort_by="p_value", top_n=5)
        vals = [r["p_value"] for r in result]
        assert vals == sorted(vals)

    def test_sort_by_combined_score_descending(self):
        items = _make_items(5)
        result = _sort_and_top(items, sort_by="combined_score", top_n=5)
        vals = [r["combined_score"] for r in result]
        assert vals == sorted(vals, reverse=True)

    def test_top_n_limits_output(self):
        items = _make_items(10)
        result = _sort_and_top(items, sort_by="adj_p_value", top_n=3)
        assert len(result) == 3

    def test_top_n_larger_than_items(self):
        items = _make_items(3)
        result = _sort_and_top(items, sort_by="adj_p_value", top_n=10)
        assert len(result) == 3

    def test_top_n_minimum_1(self):
        items = _make_items(5)
        result = _sort_and_top(items, sort_by="adj_p_value", top_n=0)
        assert len(result) >= 1

    def test_empty_items(self):
        result = _sort_and_top([], sort_by="adj_p_value", top_n=10)
        assert result == []

    def test_none_adj_p_value_sorted_last(self):
        items = [
            {**_make_items(1)[0],
             "adj_p_value": None, "p_value": None, "combined_score": None, "term": "Null Item"},
            {**_make_items(1)[0], "adj_p_value": 0.001, "term": "Good Item"},
        ]
        result = _sort_and_top(items, sort_by="adj_p_value", top_n=2)
        assert result[0]["term"] == "Good Item"

    def test_default_sort_key_is_adj_p_value(self):
        # Anything other than combined_score / p_value falls back to adj_p_value ordering
        items = _make_items(4)
        r1 = _sort_and_top(items, sort_by="adj_p_value", top_n=4)
        r2 = _sort_and_top(items, sort_by="unknown_key", top_n=4)
        # Both should produce the same ordering
        assert [i["term"] for i in r1] == [i["term"] for i in r2]


# ===========================================================================
# _run  (integration-style with httpx mocked)
# ===========================================================================

class TestRun:
    """
    These tests mock httpx.Client so no real network calls are made.
    """

    LIB = "WikiPathways_2024_Human"

    def _make_enrich_response(self, lib: str) -> Dict[str, Any]:
        return {
            lib: [
                _make_row(rank=i + 1, term=f"Path {i}", adj_p_value=(i + 1) * 0.01)
                for i in range(5)
            ]
        }

    def _setup_mock_client(self, mock_client_cls, lib: str):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        # addList response
        add_resp = MagicMock()
        add_resp.status_code = 200
        add_resp.json.return_value = {"userListId": "abc123"}

        # enrich response
        enrich_resp = MagicMock()
        enrich_resp.status_code = 200
        enrich_resp.json.return_value = self._make_enrich_response(lib)

        mock_client.post.return_value = add_resp
        mock_client.get.return_value = enrich_resp

        return mock_client

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_successful_run_returns_ok(self, mock_client_cls):
        self._setup_mock_client(mock_client_cls, self.LIB)
        result = _run(
            {"genes": ["TP53", "BRCA1"], "libraries": [self.LIB]},
            {},
            log=lambda msg: None,
        )
        assert result["ok"] is True
        assert result["userListId"] == "abc123"
        assert self.LIB in result["results"]

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_meta_populated(self, mock_client_cls):
        self._setup_mock_client(mock_client_cls, self.LIB)
        result = _run(
            {"genes": ["TP53", "BRCA1"], "libraries": [self.LIB], "top_n": 3, "sort_by": "p_value"},
            {},
            log=lambda msg: None,
        )
        assert result["meta"]["n_genes"] == 2
        assert result["meta"]["top_n"] == 3
        assert result["meta"]["sort_by"] == "p_value"
        assert result["meta"]["libraries"] == [self.LIB]

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_top_n_respected(self, mock_client_cls):
        self._setup_mock_client(mock_client_cls, self.LIB)
        result = _run(
            {"genes": ["TP53", "BRCA1"], "libraries": [self.LIB], "top_n": 2},
            {},
            log=lambda msg: None,
        )
        items = result["results"][self.LIB]["items"]
        assert len(items) <= 2

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_return_mode_all_does_not_apply_top_n(self, mock_client_cls):
        self._setup_mock_client(mock_client_cls, self.LIB)
        result = _run(
            {
                "genes": ["TP53", "BRCA1"],
                "libraries": [self.LIB],
                "top_n": 1,
                "return_mode": "all",
            },
            {},
            log=lambda msg: None,
        )
        # In "all" mode, the items are not truncated to top_n
        items = result["results"][self.LIB]["items"]
        assert len(items) == 5  # all 5 rows from the mock

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_genes_stripped_and_blanks_removed(self, mock_client_cls):
        mock_client = self._setup_mock_client(mock_client_cls, self.LIB)
        _run(
            {"genes": [" TP53 ", "", "BRCA1"], "libraries": [self.LIB]},
            {},
            log=lambda msg: None,
        )
        # Inspect the data posted to addList
        post_call_kwargs = mock_client.post.call_args
        files = post_call_kwargs[1].get("files") or post_call_kwargs.kwargs.get("files")
        gene_blob = files["list"][1]
        assert "TP53" in gene_blob
        assert "BRCA1" in gene_blob
        # Empty string should not appear as a gene
        lines = [line for line in gene_blob.strip().splitlines() if line]
        assert "" not in lines

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_default_libraries_used_when_not_provided(self, mock_client_cls):
        # Need to handle two library calls; return the first lib's response for any get
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        add_resp = MagicMock()
        add_resp.status_code = 200
        add_resp.json.return_value = {"userListId": "xyz"}

        def enrich_side_effect(url, params=None):
            lib = (params or {}).get("backgroundType", "WikiPathways_2024_Human")
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {lib: [_make_row()]}
            return resp

        mock_client.post.return_value = add_resp
        mock_client.get.side_effect = enrich_side_effect

        result = _run({"genes": ["TP53"]}, {}, log=lambda msg: None)
        assert "WikiPathways_2024_Human" in result["results"]
        assert "Reactome_2022" in result["results"]

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_addlist_http_error_raises(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        bad_resp = MagicMock()
        bad_resp.status_code = 500
        bad_resp.text = "Internal Server Error"
        mock_client.post.return_value = bad_resp

        with pytest.raises(RuntimeError, match="addList failed"):
            _run({"genes": ["TP53"], "libraries": [self.LIB]}, {}, log=lambda msg: None)

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_missing_user_list_id_raises(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        add_resp = MagicMock()
        add_resp.status_code = 200
        add_resp.json.return_value = {}  # No userListId key
        mock_client.post.return_value = add_resp

        with pytest.raises(RuntimeError, match="userListId"):
            _run({"genes": ["TP53"], "libraries": [self.LIB]}, {}, log=lambda msg: None)

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_enrich_http_error_raises(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        add_resp = MagicMock()
        add_resp.status_code = 200
        add_resp.json.return_value = {"userListId": "abc"}
        mock_client.post.return_value = add_resp

        bad_resp = MagicMock()
        bad_resp.status_code = 429
        bad_resp.text = "Too Many Requests"
        mock_client.get.return_value = bad_resp

        with pytest.raises(RuntimeError, match="enrich failed"):
            _run({"genes": ["TP53"], "libraries": [self.LIB]}, {}, log=lambda msg: None)

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_log_callable_called(self, mock_client_cls):
        self._setup_mock_client(mock_client_cls, self.LIB)
        log_messages = []
        _run(
            {"genes": ["TP53"], "libraries": [self.LIB]},
            {},
            log=log_messages.append,
        )
        assert len(log_messages) >= 2  # at least addList + enrich messages

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_custom_base_url_used(self, mock_client_cls):
        mock_client = self._setup_mock_client(mock_client_cls, self.LIB)
        _run(
            {
                "genes": ["TP53"],
                "libraries": [self.LIB],
                "_enrichr_base_url": "https://my-enrichr.example.com",
            },
            {},
            log=lambda msg: None,
        )
        post_url = mock_client.post.call_args[0][0]
        assert "my-enrichr.example.com" in post_url

    @patch("toolserver.tools.enrichr_pathway.httpx.Client")
    def test_result_structure(self, mock_client_cls):
        self._setup_mock_client(mock_client_cls, self.LIB)
        result = _run(
            {"genes": ["TP53", "MYC"], "libraries": [self.LIB]},
            {},
            log=lambda msg: None,
        )
        lib_result = result["results"][self.LIB]
        for key in ("library", "columns", "sort_by", "top_n", "n_terms", "items"):
            assert key in lib_result, f"Missing key: {key}"