# Production v5 comparison source fixture

This directory contains only the 10 unchanged Python source helpers required to execute the original production v5 ChatAgent and its real ConversationStore, lexical retrieval fallback and original chart engines in an isolated evaluation process. SOURCE_MANIFEST.json records each exact original byte hash and size from the read-only work/server-source/hermes snapshot. It contains no user archive, history, image, token, credential or database.

The comparison tool verifies every helper against this manifest before executing the legacy arm. Only the expanded arm changes two history constants in memory. This fixture is never imported by the Core business application. The legacy directory is excluded from ordinary test discovery; tests/test_core_provider_comparison.py explicitly invokes this isolated source.
