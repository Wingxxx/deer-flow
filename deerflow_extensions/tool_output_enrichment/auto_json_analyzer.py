"""AutoJsonAnalyzer — automatic field-type detection with 10 layers of protection.

Replaces hard-coded field enumeration (``"type", "os", "status", ...``) with
sampling-based automatic detection.  Bool detection precedes int detection
(Python ``bool`` is a subclass of ``int``).  Distribution stats use random
sampling (O(1000)) instead of full iteration (O(N)) for performance.

Protections (in order):
  1. len(text) > max_size → bail (prevent OOM)
  2. lstrip → tolerate leading whitespace
  3. first char != '[' → bail (fast path)
  4. try json.loads → bail on parse error
  5. isinstance list check → bail on non-array JSON
  6. empty array → return empty summary
  7. data[0] isinstance dict → skip field analysis for primitive arrays
  8. keys[:15] truncation → prevent ultra-wide schema
  9. random.sample for distribution stats → O(1000) not O(N)
  10. top-10 distribution cap → summary size bounded
"""

from __future__ import annotations

import json
import random


def _analyze_dict_array(data: list, original_text: str) -> str:
    """Analyze a list of dicts and produce an enriched summary line.

    This is the core field-analysis logic, shared by top-level arrays
    and embedded arrays inside JSON objects.

    Protections 6-10 are applied here.
    """
    n = len(data)

    # --- Protection 6: empty array --------------------------------------------
    if n == 0:
        return "[Summary: empty array (0 items)]\n" + original_text

    # --- Protection 7: dict type check for first element ----------------------
    if not isinstance(data[0], dict):
        return f"[Summary: {n} items (not dict)]\n" + original_text

    # --- Protection 8: keys[:15] truncation -----------------------------------
    fields = list(data[0].keys())
    summary_parts = [f"[Summary: {n} items fields: {', '.join(fields[:15])}"]
    if len(fields) > 15:
        summary_parts.append("...")

    # --- Automatic field analysis (first 100 items for type detection) --------
    type_sample = data[:100]
    for field in fields[:15]:
        values = [
            item.get(field)
            for item in type_sample
            if isinstance(item, dict) and item.get(field) is not None
        ]
        if not values:
            continue

        # bool BEFORE int (Python bool is subclass of int)
        if all(isinstance(v, bool) for v in values):
            t = sum(1 for v in values if v)
            summary_parts.append(f"{field}: true={t}, false={len(values) - t}")

        # numeric (explicitly exclude bool via the "not any(isinstance(v, bool))" guard)
        elif all(isinstance(v, (int, float)) for v in values) and not any(
            isinstance(v, bool) for v in values
        ):
            nums = [v for v in values if isinstance(v, (int, float))]
            mn, mx = min(nums), max(nums)
            if mn == mx:
                summary_parts.append(f"{field}: all={mn}")
            else:
                avg = sum(nums) / len(nums)
                # detect 0/1 pattern (likely semantic boolean in JSON)
                unique_vals = set(nums)
                if unique_vals <= {0, 1}:
                    ones = sum(1 for v in nums if v == 1)
                    summary_parts.append(
                        f"{field}: 0={len(nums) - ones}, 1={ones} (0/1)"
                    )
                else:
                    summary_parts.append(f"{field}: {mn}-{mx}, avg={avg:.0f}")

        # string-like: low cardinality → sampled distribution; high → skip
        else:
            str_vals = [str(v) for v in values]
            uniq = set(str_vals)
            if len(uniq) <= 20:
                # --- Protection 9: random.sample for distribution stats -------
                # --- Protection 10: top-10 distribution cap -------------------
                sample_for_dist = random.sample(data, min(1000, len(data)))
                dist: dict[str, int] = {}
                for item in sample_for_dist:
                    if isinstance(item, dict):
                        val = str(item.get(field))
                        dist[val] = dist.get(val, 0) + 1
                top = sorted(dist.items(), key=lambda x: -x[1])[:10]
                dist_str = ", ".join(f"{k}={v}" for k, v in top)
                sample_note = " (sampled)" if len(data) > 1000 else ""
                summary_parts.append(f"{field}: {dist_str}{sample_note}")
            # high cardinality (>20) → skip, no meaningful summary

    return " ".join(summary_parts) + "]\n" + original_text


def _summarise_json_array(text: str, max_size: int = 200_000) -> str:
    """Auto-detect JSON array (or object containing array), inject summary.

    Supports two shapes:
      - Top-level array:  [{...}, {...}, ...]
      - Object holding array:  {"total": N, "rows": [{...}, ...]}

    Protections (in order):
      1. len(text) > max_size → bail (prevent OOM)
      2. lstrip → tolerate leading whitespace
      3. first char not '[' or '{' → bail (fast path)
      4. try json.loads → bail on parse error
      5. isinstance list check (for arrays) OR dict check (for objects)
      6. empty array → return empty summary
      7. data[0] isinstance dict → skip field analysis for primitive arrays
      8. keys[:15] truncation → prevent ultra-wide schema
      9. random.sample for distribution stats → O(1000) not O(N)
      10. top-10 distribution cap → summary size bounded
    """

    # --- Protection 1: size precheck ------------------------------------------
    if max_size > 0 and len(text) > max_size:
        return text

    # --- Protection 2: lstrip -------------------------------------------------
    stripped = text.lstrip()
    if not stripped:
        return text

    first = stripped[0]

    # --- Protection 3a: top-level JSON array ----------------------------------
    if first == "[":
        try:
            data = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return text
        if not isinstance(data, list):
            return text
        return _analyze_dict_array(data, text)

    # --- Protection 3b: JSON object containing array fields -------------------
    if first == "{":
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return text
        if not isinstance(obj, dict):
            return text
        # Scan for the first array-valued field
        for field_name, field_value in obj.items():
            if isinstance(field_value, list) and len(field_value) > 0:
                # Found an array -- analyze it
                enriched = _analyze_dict_array(field_value, text)
                return enriched
            elif isinstance(field_value, list) and len(field_value) == 0:
                # Empty array inside object
                encoded = json.dumps(obj)
                return f"[Summary: {field_name} empty (0 items)]\n" + encoded
        # No array found in object -- fall through

    # --- Not a JSON array or object we understand, pass through ---------------
    return text
