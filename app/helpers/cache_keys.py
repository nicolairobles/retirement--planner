"""
Shared cache-key construction for Streamlit @st.cache_data.

Every page that caches on inputs must use the SAME tuple construction,
or two pages will hash different keys for the same scenario and return
stale/inconsistent results.
"""

from __future__ import annotations


def inputs_cache_key(inputs: dict) -> tuple:
    """Stable, hashable cache key from an inputs dict.

    Sorts by key, includes all scalar values. Excludes list/dict values
    that aren't hashable. This is the ONE place that defines how inputs
    become a cache key — every page imports this instead of rolling its own.
    """
    return tuple(sorted(
        (k, v) for k, v in inputs.items()
        if not isinstance(v, (list, dict))
    ))
