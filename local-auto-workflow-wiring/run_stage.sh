#!/usr/bin/env bash
# Actual shell entrypoint used by the OFF/uninstalled workflow. No eval, no install.
set -euo pipefail
: "${CONFIG_FILE:?Explicit production config path required}"
case "${1:-}" in
  resolve|build|validate|preflight) ;;
  *) echo 'Expected resolve, build, validate, or preflight' >&2; exit 2 ;;
esac
exec python3 local-auto-workflow-wiring/workflow_driver.py "$1" \
  --config "$CONFIG_FILE" --work "${WORK_DIR:-auto-work}" \
  --tracker "${TRACKER_DIR:-source}" --artifact "${BUILD_ARTIFACT_DIR:-incoming}" \
  --dest "${QA_ARTIFACT_DIR:-qa-artifact}"
