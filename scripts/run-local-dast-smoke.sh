#!/usr/bin/env bash

set -euo pipefail

readonly BUILD_REPOSITORY="build-dynamic-application-security-testing"
readonly SIDECAR_REPOSITORY="dast-config-manager"
readonly ZAP_CONTAINER_NAME="zap"
readonly ZAP_HOST="${ZAP_HOST:-localhost:11000}"
readonly START_WAIT_SECONDS="${START_WAIT_SECONDS:-180}"
readonly SMOKE_TARGET_URL="${SMOKE_TARGET_URL:-http://example.com/}"
readonly SIDECAR_COMPOSE_IMAGE="dockerhub.tax.service.gov.uk/compose:1.29.2"
readonly SIDECAR_COMPOSE_FALLBACK_IMAGE="docker/compose:1.29.2"

parent_directory="${PWD}"
verbose=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--parent-dir DIRECTORY]

Run the local DAST image smoke and sidecar lifecycle checks.

The parent directory must contain:
  ${BUILD_REPOSITORY}/
  ${SIDECAR_REPOSITORY}/

Options:
  --parent-dir DIRECTORY  Parent directory containing both repositories.
  -v, --verbose           Show full command output and diagnostics.
  -h, --help              Show this help.
EOF
}

log() {
    printf '[local-dast] %s\n' "$*"
}

stage() {
    printf '\n[local-dast] === %s ===\n' "$*"
}

fail() {
    printf '[local-dast] ERROR: %s\n' "$*" >&2
    exit 1
}

while (($# > 0)); do
    case "$1" in
        --parent-dir)
            (($# >= 2)) || fail "--parent-dir requires a directory"
            parent_directory="$2"
            shift 2
            ;;
        -v|--verbose)
            verbose=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

build_directory="${parent_directory}/${BUILD_REPOSITORY}"
sidecar_directory="${parent_directory}/${SIDECAR_REPOSITORY}"
sidecar_zap_host="${SIDECAR_ZAP_HOST:-}"
build_pipfile_existed=false

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

require_repository() {
    local directory="$1"
    local name="$2"

    [[ -d "$directory" ]] || fail "${name} repository not found: ${directory}"
    [[ -f "${directory}/Makefile" ]] || fail "${name} repository has no Makefile: ${directory}"
}

require_command docker
require_command curl
require_command make
require_repository "$build_directory" "build"
require_repository "$sidecar_directory" "sidecar"

if [[ -e "${build_directory}/Pipfile" ]]; then
    build_pipfile_existed=true
fi

if [[ -z "$sidecar_zap_host" ]]; then
    host_ip="$(ifconfig 2>/dev/null | grep -m 1 -oE 'inet (10\.[0-9]+|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.[0-9]+\.[0-9]+' | grep -oE '[0-9.]+')" || true
    sidecar_zap_host="${host_ip:-host.docker.internal}:11000"
fi

if "$verbose"; then
    docker info || fail "Docker is not running"
elif ! docker info >/dev/null 2>&1; then
    fail "Docker is not running"
fi

cleanup() {
    if docker ps --format '{{.Names}}' | grep -Fxq "$ZAP_CONTAINER_NAME"; then
        log "Stopping ZAP container"
        make -C "$build_directory" stop >/dev/null 2>&1 || true
    fi
    if [[ "$build_pipfile_existed" == false && -f "${build_directory}/Pipfile" ]]; then
        log "Removing Pipfile created during the run"
        rm -f "${build_directory}/Pipfile"
    fi
}

trap cleanup EXIT

stage "1/8 Build and start the local DAST image"
if ! make -C "$build_directory" start TEST_WAIT_THRESHOLD="$START_WAIT_SECONDS" ZAP_HOST="$ZAP_HOST"; then
    log "Docker startup failed; checking the container state"
    docker inspect "$ZAP_CONTAINER_NAME" \
        --format '[local-dast] container exit={{.State.ExitCode}} oom={{.State.OOMKilled}}' \
        2>/dev/null || true
    if docker inspect "$ZAP_CONTAINER_NAME" --format '{{.State.ExitCode}}' 2>/dev/null | grep -Fxq 137; then
        log "Meaning: Docker killed ZAP for exceeding the memory available to the container runtime."
        log "Try increasing Colima memory, for example: colima stop && colima start --memory 8"
    fi
    log "Docker startup logs:"
    docker logs "$ZAP_CONTAINER_NAME" 2>&1 || true
    exit 1
fi

stage "2/8 Check the ZAP API"
version_response="$(curl --fail --silent "http://${ZAP_HOST}/JSON/core/view/version/?")" \
    || fail "ZAP API is not responding at http://${ZAP_HOST}"
printf '%s\n' "$version_response"

stage "3/8 Check passive scanners"
scanner_response="$(curl --fail --silent "http://${ZAP_HOST}/JSON/pscan/view/scanners/?")" \
    || fail "ZAP passive-scanner API is not responding"
if [[ "$scanner_response" != *'"scanners"'* ]]; then
    fail "ZAP returned an unexpected passive-scanner response"
fi
log "Passive-scanner API is responding"
if "$verbose"; then
    printf '%s\n' "$scanner_response"
fi

stage "4/8 Review ZAP startup diagnostics"
startup_log="$(docker logs "$ZAP_CONTAINER_NAME" 2>&1 || true)"
if "$verbose"; then
    log "Full ZAP container log:"
    printf '%s\n' "$startup_log"
    startup_messages="$(printf '%s\n' "$startup_log" | grep -E '(^|[[:space:]])(WARN|ERROR|FATAL|FAILED|EXCEPTION)([[:space:]]|$)' || true)"
else
    startup_messages="$(printf '%s\n' "$startup_log" | grep -E '(^|[[:space:]])(WARN|ERROR|FATAL|FAILED|EXCEPTION)([[:space:]]|$)' || true)"
fi

if [[ -n "$startup_messages" ]]; then
    printf '%s\n' "$startup_messages"
    fail "ZAP startup reported errors; the local image is not healthy enough for sidecar testing"
else
    log "No startup warnings or errors reported"
fi

stage "5/8 Send a proxied smoke request"
log "Requesting ${SMOKE_TARGET_URL} through ZAP"
if "$verbose"; then
    curl --fail --show-error --proxy "http://${ZAP_HOST}" "$SMOKE_TARGET_URL" \
        || fail "The proxied smoke request failed; check network access or override SMOKE_TARGET_URL"
else
    curl --fail --silent --show-error --proxy "http://${ZAP_HOST}" "$SMOKE_TARGET_URL" >/dev/null \
        || fail "The proxied smoke request failed; check network access or override SMOKE_TARGET_URL"
fi
log "Smoke request completed"

stage "6/8 Ensure sidecar build dependencies"
if docker image inspect "$SIDECAR_COMPOSE_IMAGE" >/dev/null 2>&1; then
    log "Found ${SIDECAR_COMPOSE_IMAGE} locally"
else
    log "Pulling ${SIDECAR_COMPOSE_IMAGE}"
    if ! docker pull "$SIDECAR_COMPOSE_IMAGE"; then
        log "The internal Compose image is unavailable; trying ${SIDECAR_COMPOSE_FALLBACK_IMAGE}"
        if ! docker pull "$SIDECAR_COMPOSE_FALLBACK_IMAGE"; then
            fail "Unable to download either sidecar Compose build dependency"
        fi
        docker tag "$SIDECAR_COMPOSE_FALLBACK_IMAGE" "$SIDECAR_COMPOSE_IMAGE"
        log "Tagged ${SIDECAR_COMPOSE_FALLBACK_IMAGE} as ${SIDECAR_COMPOSE_IMAGE} for the sidecar build"
    fi
fi

stage "7/8 Configure scanners through dast-config-manager"
log "Building the sidecar Pipenv image"
if ! make -C "$sidecar_directory" pipenv; then
    log "Sidecar environment build failed."
    log "Meaning: a sidecar build dependency or Python package could not be downloaded."
    exit 1
fi

sidecar_pipenv() {
    docker run --interactive --rm \
        --user "$(id -u):$(id -g)" \
        --env HOME=/tmp \
        --env PIPENV_VENV_IN_PROJECT=1 \
        --env "PYTHONPATH=${sidecar_directory}/zap/" \
        --env "ZAP_HOST=${sidecar_zap_host}" \
        --volume "${sidecar_directory}:${sidecar_directory}" \
        --workdir "${sidecar_directory}" \
        pipenv \
        "$@"
}

sidecar_python() {
    sidecar_pipenv run python "$@"
}

log "Using sidecar ZAP address: ${sidecar_zap_host}"
log "Installing sidecar Python dependencies in the runtime environment"
if ! sidecar_pipenv install --ignore-pipfile --dev; then
    log "Sidecar Python dependency installation failed."
    log "Meaning: the sidecar could not create its runtime environment or download a locked dependency."
    exit 1
fi

if ! sidecar_python ./zap/reset_scanners.py -f ./zap/configs/sm-frontend.json; then
    log "Sidecar scanner configuration failed."
    log "Meaning: this is a dast-config-manager dependency or connectivity failure, not a ZAP scanner failure."
    exit 1
fi

stage "8/8 Run the sidecar report lifecycle"
if ! sidecar_python ./zap/client.py --log-proxied-urls; then
    fail "The sidecar could not record proxied URLs"
fi
if ! sidecar_python ./zap/client.py --wait-for-report 300 1; then
    fail "The sidecar timed out waiting for passive scanning to complete"
fi
if ! sidecar_python ./zap/client.py --generate-report; then
    fail "The sidecar could not generate the DAST report"
fi

finding_warning=0
if ! sidecar_python ./zap/client.py --determine-result --fail-on Low; then
    finding_warning=1
    log "WARNING: the smoke target has findings at or above the Low threshold"
    log "Meaning: ZAP and the sidecar completed successfully; review the generated report for scanner findings."
fi

if "$verbose"; then
    curl --fail "http://${ZAP_HOST}/JSON/core/action/shutdown/" \
        || fail "Unable to shut down ZAP through its API"
else
    curl --fail --silent "http://${ZAP_HOST}/JSON/core/action/shutdown/" >/dev/null \
        || fail "Unable to shut down ZAP through its API"
fi

if ((finding_warning)); then
    printf '\n[local-dast] PASS WITH WARNINGS: smoke and sidecar lifecycle completed; findings were reported\n'
else
    printf '\n[local-dast] PASS: local DAST smoke and sidecar lifecycle checks passed\n'
fi
