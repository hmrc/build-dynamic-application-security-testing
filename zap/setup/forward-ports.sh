#!/usr/bin/env bash

#
# Enable port forwarding from localhost back to remote host.
#
# This is needed if client is referring to localhost URLs, which when passed to
# ZAP in its own container needs to be sent back to original (local)host where
# real services are running.
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

# Create config for forwarder rinitd from passed ports
enable_forwading() {
    set -o errexit
    local remote_host="${1}"
    local ports_to_forward="${2}"
    local port

    IFS=' ' read -r -a PORTS_ARRAY <<< "${ports_to_forward}"
    for port in "${PORTS_ARRAY[@]}"; do
        echo "Mapping localhost:${port} to ${remote_host}:${port}"
        echo "localhost ${port} ${remote_host} ${port}" >> ./rinetd.conf
    done

    rinetd --conf-file ./rinetd.conf --foreground &
}

main() {
    set -o errexit

    if [[ "${ZAP_FORWARD_ENABLE:-}" != "true" ]]; then
        echo "ZAP_FORWARD_ENABLE is not set to 'true': port forwarding skipped"
        return
    fi

    # Check that all required variables are set.
    REQUIRED_VARS=(
        HOST_IP
        ZAP_FORWARD_PORTS
    )
    for variable_name in "${REQUIRED_VARS[@]}"; do
        if ! is_var_not_empty "${variable_name}"; then
            error "variable ${variable_name} is empty"
        fi
    done

    enable_forwading "${HOST_IP}" "${ZAP_FORWARD_PORTS}"

}

echo "${0}: start"
main
echo "${0}: success"
