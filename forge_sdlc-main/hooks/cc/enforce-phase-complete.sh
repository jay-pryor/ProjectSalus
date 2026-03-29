#!/bin/bash
# Forge Phase Completion Enforcement Hook (v3)
# Fires on git commit — blocks if commit message contains "complete" or
# "mark S##" AND the corresponding evidence + reviews are missing.
#
# Also blocks if PHASE_INDEX.md is being committed with a status change
# to "completed" without evidence files existing.
#
# Global: install in ~/.claude/settings.json PreToolUse on Bash(git commit:*)
# Exit 0 = allow, Exit 2 = block

set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")

# Only check git commit commands
if [[ "$TOOL_NAME" != "Bash" ]]; then
  exit 0
fi
if ! echo "$COMMAND" | grep -qE "git commit"; then
  exit 0
fi
if [[ ! -d ".forge" ]] && [[ ! -f "PHASE_INDEX.md" ]] && [[ ! -d "phases" ]]; then
  exit 0
fi

# Check if PHASE_INDEX.md is staged with status changes to completed
STAGED=$(git diff --cached --name-only 2>/dev/null || true)
if ! echo "$STAGED" | grep -q "PHASE_INDEX"; then
  exit 0
fi

# Find the actual path to PHASE_INDEX.md (could be phases/ or root)
PHASE_FILE=$(echo "$STAGED" | grep "PHASE_INDEX" | head -1)

# Extract phases being marked complete in this commit
# Look for lines being ADDED (^+) that contain "completed"
COMPLETING=$(git diff --cached -- "$PHASE_FILE" 2>/dev/null | \
  grep "^+" | grep -i "completed" | grep -oP 'S\d+\.P\d+' | sort -u || true)

if [[ -z "$COMPLETING" ]]; then
  exit 0
fi

ISSUES=""
for PHASE in $COMPLETING; do
  STAGE=$(echo "$PHASE" | grep -oP 'S\d+')

  # Check for evidence summary
  SUMMARY="evidence/${STAGE}_summary.md"
  PHASE_SUMMARY="evidence/${PHASE}_summary.md"
  if [[ ! -f "$SUMMARY" ]] && [[ ! -f "$PHASE_SUMMARY" ]]; then
    ISSUES="${ISSUES}\n  - ${PHASE}: No evidence summary (expected ${SUMMARY} or ${PHASE_SUMMARY})"
  fi

  # Check for review evidence
  REVIEW_EVIDENCE=$(find evidence/ -name "*T99*" -o -name "*review*" 2>/dev/null | \
    grep -i "${STAGE}" || true)
  if [[ -z "$REVIEW_EVIDENCE" ]]; then
    ISSUES="${ISSUES}\n  - ${PHASE}: No T99 review evidence found for ${STAGE}"
  fi
done

if [[ -n "$ISSUES" ]]; then
  {
    echo "FORGE PHASE COMPLETION BLOCKED"
    echo ""
    echo "You are marking phases as complete but required evidence is missing:"
    echo -e "$ISSUES"
    echo ""
    echo "Required before marking a phase complete:"
    echo "  1. Evidence summary file: evidence/S##_summary.md"
    echo "  2. T99 review evidence: evidence/S##-*_T99_reviews.md"
    echo "  3. All review findings resolved (0 Critical/High)"
    echo ""
    echo "Run T98 (evidence) and T99 (reviews) first."
  } >&2
  exit 2
fi

exit 0
