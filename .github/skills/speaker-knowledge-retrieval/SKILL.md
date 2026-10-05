---
name: speaker-knowledge-retrieval
description: "Retrieve loudspeaker equations, measurement procedures, source citations, assumptions, and implementation status from the local knowledge database. Use for source-backed speaker-design questions or before applying a formula."
argument-hint: "Topic, equation, workflow stage, or source citation"
---

# Speaker Knowledge Retrieval

1. Search with `python -B -m scripts.system_design.speaker_knowledge_db search "QUERY"`; results include equations, workflow gates, limitations, and source retrieval status.
2. If the database is absent/stale, rebuild with `python -B -m scripts.system_design.speaker_knowledge_db build` from the checked-in seed.
3. Return the formula/procedure, variable units, assumptions, source IDs/citations, local implementation, and test/measurement status.
4. Do not present rule-of-thumb alignments, OCR-derived values, or unverified book tables as exact universal values. Say when the local database has no entry.

Primary map: [DESIGN_KNOWLEDGE_BASE.md](../../../docs/DESIGN_KNOWLEDGE_BASE.md). The SQLite database is an index/knowledge store, not a substitute for the underlying source books or measurement standards.