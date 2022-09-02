#!/usr/bin/env bash

#
# Wrapper script for ZAP sidecar
#

set -o errexit  # Exit immediately if any command or pipeline of commands fails
set -o nounset  # Treat unset variables and parameters as an error
set -o pipefail # Exit when command before pipe fails
# set -o xtrace   # Debug mode expand everything and print it before execution

cd "$(dirname "$0")" # Always run from script location

# Print message to STDERR and exit with non-zero code
error() {
    set -o errexit
    local message="${1}"
    echo "ERROR: ${message}" >&2
    exit 1
}

# Return 1 if variable with name passed as first argument is not set or is empty
is_var_not_empty() {
    set -o errexit
    local variable_name="${1}"
    (
        set +o nounset
        if [[ -z "${!variable_name}" ]]; then
            return 1
        fi
    )
}

main() {
    set -o errexit

    # Check that all required variables are set.
    REQUIRED_VARS=(
        ZAP_BUILD_NUMBER
        ZAP_HOME
        ZAP_JOB_BASE_NAME
        ZAP_PORT
        ZAP_STORAGE_SESSIONS_HOST
        ZAP_STORAGE_SESSIONS_API_KEY
    )
    for variable_name in "${REQUIRED_VARS[@]}"; do
        if ! is_var_not_empty "${variable_name}"; then
            error "variable ${variable_name} is empty"
        fi
    done

    # Cycle through shell scripts in setup
    for script in /zap/setup/*.sh; do
        "${script}"
    done

    # Run ZAP
    /zap/zap.sh \
        -daemon \
        -host 0.0.0.0 \
        -port "${ZAP_PORT}" \
        -config api.addrs.addr.name=.* \
        -config api.addrs.addr.regex=true \
        -config api.disablekey=true \
        -newsession "${ZAP_BUILD_NUMBER}"

    # Cycle through shell scripts in teardown
    for script in /zap/teardown/*.sh; do
        "${script}"
    done
}

echo "${0}: start"
main
echo "${0}: success"
