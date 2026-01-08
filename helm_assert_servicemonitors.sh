#!/usr/bin/env bash
#
# Helm ServiceMonitor contract assertion script
# - Renders Helm charts and asserts the ServiceMonitor and Service contract conditions
# - No cluster required (uses `helm template`)
# - Supports optional values file via --values <file> or HELM_VALUES_FILE env
#
# Exit codes:
#  0 - success (all assertions passed)
#  1 - one or more assertions failed
#  2 - prereq missing (helm/yq not installed)
#
set -euo pipefail

command -v helm >/dev/null 2>&1 || { echo "helm not found in PATH"; exit 2; }
command -v yq >/dev/null 2>&1 || { echo "yq not found in PATH"; exit 2; }

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_RENDER=$(mktemp)

cleanup() {
  rm -f "$TMP_RENDER"
}
trap cleanup EXIT

# chart path and expected label mapping
declare -A CHARTS
CHARTS["charts/poller"]="problemsolver-poller"
CHARTS["charts/webhook-worker"]="problemsolver-webhook"

USAGE() {
  cat <<EOF
Usage: $0 [--values <values-file>]

Environment:
  HELM_VALUES_FILE   optional default values override file (used if --values not provided)

Checks performed per chart:
  - When rendering with serviceMonitor.enabled=true:
      * ServiceMonitor present
      * ServiceMonitor.spec.selector.matchLabels.app == expected
      * ServiceMonitor.spec.endpoints[0].port == "metrics"
      * ServiceMonitor.spec.namespaceSelector.matchNames exists
      * Service metadata.labels.app == expected
      * Service exposes a port named "metrics"
  - When rendering with serviceMonitor.enabled=false:
      * No ServiceMonitor present

The script exits non-zero on first violation.
EOF
}

# Parse args
VALUES_FILE=${HELM_VALUES_FILE:-""}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --values)
      shift
      if [[ $# -eq 0 ]]; then
        echo "Missing value for --values"
        USAGE
        exit 1
      fi
      VALUES_FILE="$1"
      shift
      ;;
    -h|--help)
      USAGE
      exit 0
      ;;
    *)
      echo "Unknown arg: $1"
      USAGE
      exit 1
      ;;
  esac
done

render_chart() {
  local chart_path="$1"
  local enabled="$2"   # "true" or "false"
  local out_file="$3"

  if [[ -n "$VALUES_FILE" ]]; then
    if [[ ! -f "$VALUES_FILE" ]]; then
      echo "ERROR: values file specified but not found: $VALUES_FILE"
      return 1
    fi
    helm template "$chart_path" --set serviceMonitor.enabled="$enabled" --values "$VALUES_FILE" --set serviceMonitor.namespace=default > "$out_file"
  else
    helm template "$chart_path" --set serviceMonitor.enabled="$enabled" --set serviceMonitor.namespace=default > "$out_file"
  fi
}

check_chart() {
  local chart_path="$1"
  local expected_app="$2"

  echo "Checking chart: $chart_path expecting app label: $expected_app (values_file='${VALUES_FILE:-}')"

  if [[ ! -d "$chart_path" ]]; then
    echo "ERROR: Chart path not found: $chart_path"
    return 1
  fi

  # Render with ServiceMonitor enabled
  render_chart "$chart_path" true "$TMP_RENDER"
  if [[ $? -ne 0 ]]; then
    echo "ERROR: Helm template rendering failed for chart $chart_path (enabled)"
    return 1
  fi

  # 1) ServiceMonitor existence and selector.app
  sm_app=$(yq eval-all '. | select(.kind == "ServiceMonitor") | .spec.selector.matchLabels.app' "$TMP_RENDER" | sed -n '1p' || true)
  if [[ -z "$sm_app" ]]; then
    echo "ERROR: ServiceMonitor not rendered for chart $chart_path when serviceMonitor.enabled=true"
    return 1
  fi
  if [[ "$sm_app" != "$expected_app" ]]; then
    echo "ERROR: ServiceMonitor selector.app mismatch for $chart_path: found='$sm_app' expected='$expected_app'"
    return 1
  fi

  # 2) endpoints[0].port == "metrics"
  sm_port=$(yq eval-all '. | select(.kind == "ServiceMonitor") | .spec.endpoints[0].port' "$TMP_RENDER" | sed -n '1p' || true)
  if [[ "$sm_port" != "metrics" ]]; then
    echo "ERROR: ServiceMonitor endpoints[0].port mismatch for $chart_path: found='$sm_port' expected='metrics'"
    return 1
  fi

  # 3) namespaceSelector.matchNames exists and non-empty
  ns_name=$(yq eval-all '. | select(.kind == "ServiceMonitor") | .spec.namespaceSelector.matchNames[0]' "$TMP_RENDER" | sed -n '1p' || true)
  if [[ -z "$ns_name" ]]; then
    echo "ERROR: ServiceMonitor namespaceSelector.matchNames missing or empty for $chart_path"
    return 1
  fi

  # 4) Service metadata.labels.app matches expected_app
  svc_app=$(yq eval-all '. | select(.kind == "Service") | .metadata.labels.app' "$TMP_RENDER" | sed -n '1p' || true)
  if [[ -z "$svc_app" ]]; then
    echo "ERROR: Service not found in chart rendering for $chart_path"
    return 1
  fi
  if [[ "$svc_app" != "$expected_app" ]]; then
    echo "ERROR: Service.metadata.labels.app mismatch for $chart_path: found='$svc_app' expected='$expected_app'"
    return 1
  fi

  # 5) Service has a port named "metrics"
  svc_metrics=$(yq eval-all '. | select(.kind == "Service") | .spec.ports[] | select(.name == "metrics") | .name' "$TMP_RENDER" | sed -n '1p' || true)
  if [[ "$svc_metrics" != "metrics" ]]; then
    echo "ERROR: Service for $chart_path does not expose a port named 'metrics'"
    return 1
  fi

  # Render with ServiceMonitor disabled: ensure no ServiceMonitor present
  render_chart "$chart_path" false "$TMP_RENDER"
  if [[ $? -ne 0 ]]; then
    echo "ERROR: Helm template rendering failed for chart $chart_path (disabled)"
    return 1
  fi
  sm_disabled=$(yq eval-all '. | select(.kind == "ServiceMonitor") | .metadata.name' "$TMP_RENDER" || true)
  if [[ -n "$sm_disabled" ]]; then
    echo "ERROR: ServiceMonitor rendered for $chart_path when serviceMonitor.enabled=false"
    echo "Rendered ServiceMonitor names:"
    echo "$sm_disabled"
    return 1
  fi

  echo "Chart $chart_path checks passed."
  return 0
}

main() {
  local failures=0
  for chart in "${!CHARTS[@]}"; do
    expected="${CHARTS[$chart]}"
    if ! check_chart "$chart" "$expected"; then
      failures=$((failures + 1))
    fi
  done

  if [[ $failures -ne 0 ]]; then
    echo "One or more chart assertions failed."
    exit 1
  fi

  echo "All ServiceMonitor and Service assertions passed."
  exit 0
}

main