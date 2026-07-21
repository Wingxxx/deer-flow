"""Lightweight plugin chain for tool output enrichment.

Currently only AutoJsonAnalyzer is active.  The chain is designed for
extension: new enrichment plugins can be added to ``_PLUGINS`` and will
be tried in order.  First matching plugin wins (returns modified text).
"""

from __future__ import annotations

from deerflow_extensions.tool_output_enrichment.auto_json_analyzer import (
    _summarise_json_array,
)

_PLUGINS = [
    _summarise_json_array,
    # future: _summarise_markdown_table,
    # future: _summarise_csv,
]


def enrich(text: str) -> str:
    """Run text through enrichment plugin chain. First matching plugin wins.

    Each plugin receives *text* and must return either the enriched text
    (modified) or the original text (unchanged).  The chain stops at the
    first plugin that returns a different string.
    """
    for plugin in _PLUGINS:
        result = plugin(text)
        if result is not text:  # plugin modified the text
            return result
    return text
