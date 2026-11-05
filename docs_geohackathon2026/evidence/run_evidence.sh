#!/bin/bash
# Final evidence batch on one code version. Each scenario runs on the laptop's Ollama through the SSH
# tunnel when it answers, otherwise on the VPS. Memory is reset to the seed first, so the lessons the
# batch writes are the batch's own. Log: runs/evidence_final.log
cd "$(git rev-parse --show-toplevel)"
export PYTHONPATH=src
M=qwen3:4b-instruct-2507-q4_K_M
LAPTOP=http://127.0.0.1:11435
# memory reset to the seed before this batch (15:30, final code): every lesson in the evidence traces to a cited session
echo "BATCH START $(date)"
for job in "S1 lean" "S2 lean" "S5 lean" "S3 lean" "S4 lean" "S2 deep" "S6 lean" "S6 deep" "S1 deep"; do
  set -- $job
  if curl -s -m 5 "$LAPTOP/api/tags" > /dev/null; then host=$LAPTOP; where=laptop; else host=http://127.0.0.1:11434; where=vps; fi
  echo "=== $1 $2 on $where $(date +%H:%M)"
  OLLAMA_HOST=$host .venv/bin/python -m gemini_agent.scenarios "$M" "$1" "$2" 2>&1 | grep -v -i "warn"
  echo "=== done $1 $2 $(date +%H:%M)"
done
echo "BATCH DONE $(date)"
