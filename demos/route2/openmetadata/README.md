# OpenMetadata runnable demo

This directory runs the official OpenMetadata release Compose stack from a clean
state, ingests a synthetic Postgres catalog, enriches it with business semantics,
and records API/MCP-style context retrieval for an agent.

The release file is downloaded into the ignored `runtime/` directory; only the
small demo configuration and generated evidence are committed.
