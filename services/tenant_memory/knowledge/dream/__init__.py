"""Nightly DREAM STATE for the knowledge layer: drift, relevance and priority self-maintenance.

Derived data only. Every phase is idempotent, resumable, VM-friendly and logged to `dream_runs` / `dream_findings`.
Source (operational) tables are never written by this package. See docs/dream-state.md.
"""
PHASES = ("drift", "embeddings", "numbers", "relevance", "adjudicate", "consolidate", "report")
