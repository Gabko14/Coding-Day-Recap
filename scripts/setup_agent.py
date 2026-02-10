#!/usr/bin/env python3
"""Ensures the haiku-reader agent definition exists for cost-efficient session reading.
Run once; subsequent runs are a no-op."""

from pathlib import Path

AGENT_CONTENT = """\
---
name: haiku-reader
description: Fast session reader using Haiku for day-summary tasks. Use when reading CASS sessions for daily summaries.
model: haiku
---

You are a fast session reader. When given a task, execute it and report your findings concisely.
"""

agent_file = Path.home() / ".claude" / "agents" / "haiku-reader.md"

if agent_file.exists():
    print("haiku-reader agent already exists")
    raise SystemExit(0)

agent_file.parent.mkdir(parents=True, exist_ok=True)
agent_file.write_text(AGENT_CONTENT, encoding="utf-8")

print(f"Created haiku-reader agent at {agent_file}")
print("NOTE: Run /agents or restart your session to load it.")
