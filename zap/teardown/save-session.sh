#!/usr/bin/env bash

#
# Export ZAP Session and upload it to ZAP_STORAGE_SESSIONS_HOST
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

# Create an archive in session_directory based on session_name passed as
# arguments and return full path to archive in case of success.
create_session_archive() {
    set -o errexit
    local session_directory="${1}"
    local session_name="${2}"
    local session_archive="${session_name}.tar.xz"
    (
        cd "${session_directory}"
        chmod 666 "${ZAP_BUILD_NUMBER}."* # Make session data accesible from Docker volume
        tar -cJf "${session_name}.tar.xz" \
            "${ZAP_BUILD_NUMBER}.session" \
            "${ZAP_BUILD_NUMBER}.session.data" \
            "${ZAP_BUILD_NUMBER}.session.properties" \
            "${ZAP_BUILD_NUMBER}.session.script"
        echo "${PWD}/${session_archive}"
    )
}

# Upload given file to given URL
upload_file() {
    set -o errexit
    local file_path="${1}"
    local upload_url="${2}"

    local file_name
    file_name="$(basename "${file_path}")"

    timeout 300 curl \
        --silent \
        --show-error \
        --fail \
        --header "X-JFrog-Art-Api:${ZAP_STORAGE_SESSIONS_API_KEY}" \
        --request PUT \
        --upload-file "${file_path}" \
        "${upload_url}/${file_name}"
}

main() {
    set -o errexit

    if [[ "${ZAP_SAVE_SESSION:-}" != "true" ]]; then
        echo "ZAP_SAVE_SESSION is not set to 'true': saving skipped"
        return
    fi

    # Check that all required variables are set.
    REQUIRED_VARS=(
        ZAP_BUILD_NUMBER
        ZAP_HOME
        ZAP_JOB_BASE_NAME
        ZAP_STORAGE_SESSIONS_HOST
        ZAP_STORAGE_SESSIONS_API_KEY
    )
    for variable_name in "${REQUIRED_VARS[@]}"; do
        if ! is_var_not_empty "${variable_name}"; then
            error "variable ${variable_name} is empty"
        fi
    done

    local archive_path
    archive_path=$(create_session_archive "${ZAP_HOME}/session" "${ZAP_BUILD_NUMBER}")

    local artifactory_job_url="https://${ZAP_STORAGE_SESSIONS_HOST}/artifactory/dynamic-application-security-testing-sessions/${ZAP_JOB_BASE_NAME}"
    upload_file "${archive_path}" "${artifactory_job_url}"
}

echo "${0}: start"
main
echo "${0}: success"
