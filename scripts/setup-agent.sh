#!/usr/bin/env bash
# Ensures the haiku-reader agent definition exists for cost-efficient session reading.
# Run once; subsequent runs are a no-op.

AGENT_FILE="$HOME/.claude/agents/haiku-reader.md"

if [ -f "$AGENT_FILE" ]; then
  echo "haiku-reader agent already exists"
  exit 0
fi

mkdir -p "$(dirname "$AGENT_FILE")"

cat > "$AGENT_FILE" << 'EOF'
---
name: haiku-reader
description: Fast session reader using Haiku for day-summary tasks. Use when reading CASS sessions for daily summaries.
model: haiku
---

You are a fast session reader. When given a task, execute it and report your findings concisely.
EOF

echo "Created haiku-reader agent at $AGENT_FILE"
echo "NOTE: Run /agents or restart your session to load it."
