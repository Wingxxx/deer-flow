"""Tests for AutoJsonAnalyzer — automatic field-type detection with 10 protections."""

from __future__ import annotations

import json

from deerflow_extensions.tool_output_enrichment.auto_json_analyzer import (
    _summarise_json_array,
)


class TestAutoJsonAnalyzer:
    """Unit tests for the _summarise_json_array function."""

    # --- Protection tests (things that should bail out) ---

    def test_non_json_text_passthrough(self) -> None:
        """Non-JSON text is returned unchanged."""
        text = "Hello, World!"
        assert _summarise_json_array(text) == text

    def test_non_array_json_passthrough(self) -> None:
        """JSON object (not array) is returned unchanged."""
        text = json.dumps({"key": "value"})
        assert _summarise_json_array(text) == text

    def test_oversized_text_bail(self) -> None:
        """Text exceeding max_size is returned unchanged."""
        text = "[" + "x" * 5000 + "]"
        assert _summarise_json_array(text, max_size=100) == text

    def test_not_json_passthrough(self) -> None:
        """Malformed JSON is returned unchanged."""
        text = "[1, 2, invalid"
        assert _summarise_json_array(text) == text

    def test_leading_whitespace_tolerant(self) -> None:
        """Leading whitespace is tolerated (lstrip)."""
        text = "  \n  [1, 2, 3]"
        result = _summarise_json_array(text)
        assert "[Summary:" in result
        assert "items (not dict)" in result

    # --- Empty / edge case tests ---

    def test_empty_array(self) -> None:
        """Empty JSON array returns 'empty array' summary."""
        result = _summarise_json_array("[]")
        assert "[Summary: empty array (0 items)]" in result

    def test_single_item_dict(self) -> None:
        """Single dict item: works but no distribution."""
        result = _summarise_json_array('[{"id": 1, "name": "test"}]')
        assert "[Summary: 1 items" in result
        assert "fields:" in result

    def test_primitive_array(self) -> None:
        """Array of primitives (not dicts) returns count but no field analysis."""
        result = _summarise_json_array("[1, 2, 3, 4, 5]")
        assert "[Summary: 5 items (not dict)]" in result

    # --- Bool-before-int tests (Python bool subclass of int) ---

    def test_bool_detected_before_int(self) -> None:
        """bool fields produce true/false counts, not numeric 0-1."""
        data = [{"active": True}, {"active": False}, {"active": True}]
        result = _summarise_json_array(json.dumps(data))
        assert "active: true=2, false=1" in result

    def test_mixed_bool_and_int_detected_correctly(self) -> None:
        """Mixed bool/int in sample: bool check sees non-bool → falls through to numeric."""
        data = [{"val": True}, {"val": 5}, {"val": 3}]
        result = _summarise_json_array(json.dumps(data))
        # Since not all are bool, it falls through to numeric
        # But True is also int(1), so we get [True(1), 5, 3] as nums
        assert "val:" in result

    # --- Numeric field tests ---

    def test_all_same_numeric(self) -> None:
        """Numeric field with all same value → 'all=N'."""
        data = [{"score": 5}, {"score": 5}, {"score": 5}]
        result = _summarise_json_array(json.dumps(data))
        assert "score: all=5" in result

    def test_01_pattern(self) -> None:
        """0/1 numeric pattern → annotated '(0/1)'."""
        data = [{"flag": 0}, {"flag": 1}, {"flag": 0}, {"flag": 1}, {"flag": 1}]
        result = _summarise_json_array(json.dumps(data))
        assert "(0/1)" in result
        assert "0=2, 1=3" in result

    def test_numeric_range(self) -> None:
        """Numeric range → 'min-max, avg=N'."""
        data = [{"val": 10}, {"val": 20}, {"val": 30}]
        result = _summarise_json_array(json.dumps(data))
        assert "val: 10-30" in result
        assert "avg=20" in result

    # --- String / distribution tests ---

    def test_low_cardinality_distribution(self) -> None:
        """Low cardinality string field → distribution summary."""
        data = [{"type": "A"}, {"type": "B"}, {"type": "A"}, {"type": "A"}, {"type": "B"}]
        result = _summarise_json_array(json.dumps(data))
        assert "type:" in result
        assert "A=" in result
        assert "B=" in result

    # --- Nested / non-scalar tolerance ---

    def test_nested_object_field_skipped(self) -> None:
        """Nested object values are skipped, not crashed."""
        data = [{"nested": {"a": 1}}, {"nested": {"b": 2}}]
        result = _summarise_json_array(json.dumps(data))
        # Should not crash; nested field won't be a simple type
        assert "[Summary:" in result

    def test_heterogeneous_missing_fields(self) -> None:
        """Items with missing fields don't cause crash."""
        data = [
            {"a": 1, "b": "x"},
            {"a": 2},  # missing 'b'
            {"b": "y"},  # missing 'a'
        ]
        result = _summarise_json_array(json.dumps(data))
        assert "[Summary:" in result

    # --- Large sample distribution note ---

    def test_large_sample_annotation(self) -> None:
        """When data > 1000 items and sampling is used, '(sampled)' is annotated."""
        # Generate >1000 items with a low-cardinality string field
        data = [{"type": "A" if i % 2 == 0 else "B"} for i in range(1100)]
        result = _summarise_json_array(json.dumps(data))
        assert "(sampled)" in result

    # --- Fields truncation ---

    def test_fields_truncation_at_15(self) -> None:
        """Dicts with >15 keys get '...' in summary."""
        item = {f"field_{i}": i for i in range(20)}
        data = [item]
        result = _summarise_json_array(json.dumps(data))
        # The summary line (before the newline) should have '...'
        summary_line = result.split("\n")[0]
        assert "..." in summary_line
        assert "field_0" in summary_line
        assert "field_14" in summary_line
        # field_15 should not appear in the summary fields list (keys[:15])
        # Note: it WILL be in the raw JSON body appended after the summary,
        # so check the summary line only.
        assert "field_15" not in summary_line

    # --- Object containing array tests (mcp_sys_client_list pattern) ---

    def test_object_with_array_detected(self) -> None:
        """JSON object containing an array field extracts summary from the array."""
        obj = {"total": 3, "rows": [{"name": "A"}, {"name": "B"}, {"name": "C"}]}
        result = _summarise_json_array(json.dumps(obj))
        assert "Summary: 3 items" in result
        assert "name:" in result

    def test_object_with_empty_array(self) -> None:
        """JSON object with empty array returns empty summary."""
        obj = {"total": 0, "rows": []}
        result = _summarise_json_array(json.dumps(obj))
        assert "empty" in result.lower()

    def test_object_with_no_array_passthrough(self) -> None:
        """JSON object without array fields is passed through unchanged."""
        obj = {"status": "ok", "message": "no data"}
        text = json.dumps(obj)
        result = _summarise_json_array(text)
        assert result == text

    def test_object_with_primitive_array_passthrough(self) -> None:
        """JSON object containing primitive (non-dict) array skips field analysis."""
        obj = {"ids": [1, 2, 3, 4, 5]}
        result = _summarise_json_array(json.dumps(obj))
        assert "Summary:" in result
        assert "(not dict)" in result

    def test_object_with_array_01_pattern(self) -> None:
        """0/1 numeric pattern inside embedded array is annotated."""
        obj = {"total": 3, "items": [{"flag": 0}, {"flag": 1}, {"flag": 0}]}
        result = _summarise_json_array(json.dumps(obj))
        assert "(0/1)" in result
        assert "flag:" in result
