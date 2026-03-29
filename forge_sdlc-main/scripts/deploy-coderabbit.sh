#!/usr/bin/env bash
set -euo pipefail

# deploy-coderabbit.sh — Deploy CodeRabbit configs to all OnPulse projects
# Usage: ./deploy-coderabbit.sh [--dry-run]

TEMPLATE_DIR="/home/deploy/forge-sdlc/templates/coderabbit"
WORKSPACE="/home/deploy/workspace"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "[DRY RUN] No files will be written or committed."
    echo ""
fi

# ── Project-to-stack mapping ─────────────────────────────────────────────────
declare -A PROJECT_STACKS=(
    # python
    [blog-automation]=python
    [evgp-system]=python
    [geosignal]=python
    [health-dashboard]=python
    [onpulse-revenue-intelligence]=python
    # nextjs
    [onpulse-website]=nextjs
    [pulsity.io]=nextjs
    [pulsity_web-demo]=nextjs
    # fullstack
    [command-centre]=fullstack
    [ers]=fullstack
    [evgp-1-onboarding]=fullstack
    [evgp-2-processing]=fullstack
    [pulsity]=fullstack
    [rubric]=fullstack
)

UPDATED=0
SKIPPED=0

for project in "${!PROJECT_STACKS[@]}"; do
    stack="${PROJECT_STACKS[$project]}"
    target_dir="${WORKSPACE}/${project}"
    target_file="${target_dir}/.coderabbit.yaml"

    echo "── ${project} (${stack}) ──"

    # Project directory must exist
    if [[ ! -d "$target_dir" ]]; then
        echo "  SKIP: ${target_dir} does not exist"
        SKIPPED=$((SKIPPED + 1))
        echo ""
        continue
    fi

    # Start with base config
    base_file="${TEMPLATE_DIR}/base.yaml"
    if [[ ! -f "$base_file" ]]; then
        echo "  SKIP: base.yaml not found at ${base_file}"
        SKIPPED=$((SKIPPED + 1))
        echo ""
        continue
    fi

    config_content="$(cat "$base_file")"

    # Append stack-specific overlay path_instructions
    if [[ "$stack" == "fullstack" ]]; then
        # Fullstack: merge BOTH python and nextjs overlays
        overlays=("overlay-python.yaml" "overlay-nextjs.yaml")
    else
        overlays=("overlay-${stack}.yaml")
    fi

    for overlay_name in "${overlays[@]}"; do
        overlay_file="${TEMPLATE_DIR}/${overlay_name}"
        if [[ -f "$overlay_file" ]]; then
            path_section="$(sed -n '/^  path_instructions:/,/^  [^ ]/{ /^  path_instructions:/p; /^    /p; }' "$overlay_file")"
            if [[ -n "$path_section" ]]; then
                config_content="${config_content}
${path_section}"
            fi
        else
            echo "  WARN: overlay file ${overlay_file} not found"
        fi
    done

    # Append project-specific overlay if it exists
    project_overlay="${TEMPLATE_DIR}/projects/${project}.yaml"
    if [[ -f "$project_overlay" ]]; then
        project_section="$(sed -n '/^  path_instructions:/,/^  [^ ]/{ /^  path_instructions:/p; /^    /p; }' "$project_overlay")"
        if [[ -n "$project_section" ]]; then
            config_content="${config_content}
${project_section}"
        fi
    fi

    if $DRY_RUN; then
        echo "  Would write ${target_file}:"
        echo "$config_content" | sed 's/^/    /'
    else
        echo "$config_content" > "$target_file"
        echo "  Wrote ${target_file}"

        # Git add, commit, push
        (
            cd "$target_dir"
            git add .coderabbit.yaml
            git commit -m "chore: update CodeRabbit review config (${stack} stack)" || {
                echo "  WARN: nothing to commit (config unchanged?)"
            }
            git push || {
                echo "  ERROR: git push failed for ${project}"
            }
        )
    fi

    UPDATED=$((UPDATED + 1))
    echo ""
done

echo "════════════════════════════════"
echo "Summary: Updated: ${UPDATED}, Skipped: ${SKIPPED}"
echo "════════════════════════════════"
