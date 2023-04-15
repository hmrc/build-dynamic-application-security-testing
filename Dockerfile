ARG ZAP_VERSION
FROM owasp/zap2docker-stable:${ZAP_VERSION}

ENV ZAP_STORAGE_SESSIONS_HOST="artefacts.tax.service.gov.uk"
ENV ZAP_STORAGE_SESSIONS_API_KEY=""
ENV ZAP_BUNDLE="current"
ENV ZAP_HOME=/home/zap/.ZAP
ENV ZAP_PORT=11000
ENV ZAP_FORWARD_ENABLE="false"

USER root

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        jq=1.6* \
        rinetd=0.62* \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && touch /var/run/rinetd.pid \
    && chown zap:zap /var/run/rinetd.pid

USER zap

# Autogenerated by updater.py - DO NOT EDIT MANUALLY
WORKDIR /zap/plugin
ARG ASCANRULES_VERSION=53
ARG ASCANRULESBETA_VERSION=45
ARG PSCANRULES_VERSION=47
ARG PSCANRULESBETA_VERSION=32
ARG RETIRE_VERSION=0.21.0
ARG ALERTFILTERS_VERSION=15
ARG COMMONLIB_VERSION=1.14.0
ARG NETWORK_VERSION=0.7.0
ARG OAST_VERSION=0.15.0
ARG DATABASE_VERSION=0.1.0
ARG NETWORK_VERSION=0.7.0
RUN rm --force \
        ascanrules-release-*.zap \
        ascanrulesBeta-beta-*.zap \
        pscanrules-release-*.zap \
        pscanrulesBeta-beta-*.zap \
        retire-release-*.zap \
        alertFilters-release-*.zap \
        commonlib-release-*.zap \
        network-beta-*.zap \
        oast-beta-*.zap \
        database-alpha-*.zap \
        network-beta-*.zap \
    && wget --quiet \
        https://github.com/zaproxy/zap-extensions/releases/download/ascanrules-v${ASCANRULES_VERSION}/ascanrules-release-${ASCANRULES_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/ascanrulesBeta-v${ASCANRULESBETA_VERSION}/ascanrulesBeta-beta-${ASCANRULESBETA_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/pscanrules-v${PSCANRULES_VERSION}/pscanrules-release-${PSCANRULES_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/pscanrulesBeta-v${PSCANRULESBETA_VERSION}/pscanrulesBeta-beta-${PSCANRULESBETA_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/retire-v${RETIRE_VERSION}/retire-release-${RETIRE_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/alertFilters-v${ALERTFILTERS_VERSION}/alertFilters-release-${ALERTFILTERS_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/commonlib-v${COMMONLIB_VERSION}/commonlib-release-${COMMONLIB_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/network-v${NETWORK_VERSION}/network-beta-${NETWORK_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/oast-v${OAST_VERSION}/oast-beta-${OAST_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/database-v${DATABASE_VERSION}/database-alpha-${DATABASE_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/network-v${NETWORK_VERSION}/network-beta-${NETWORK_VERSION}.zap
# Autogenerated END

COPY --chown=zap:zap zap /zap

CMD ["/zap/zapw.sh"]
