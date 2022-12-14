ARG ZAP_VERSION
FROM owasp/zap2docker-stable:${ZAP_VERSION}

ENV ZAP_STORAGE_SESSIONS_HOST="artefacts.tax.service.gov.uk"
ENV ZAP_STORAGE_SESSIONS_API_KEY=""
ENV ZAP_BUNDLE="current"
ENV ZAP_HOME=/home/zap/.ZAP
ENV ZAP_PORT=11000

USER root

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
    jq=1.5* \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER zap

# Autogenerated by updater.py - DO NOT EDIT MANUALLY
WORKDIR /zap/plugin
ARG ASCANRULES_VERSION=35
ARG ASCANRULESBETA_VERSION=29
ARG PSCANRULES_VERSION=28
ARG PSCANRULESBETA_VERSION=21
RUN rm --force \
    ascanrules-release-*.zap \
    ascanrulesBeta-beta-*.zap \
    pscanrules-release-*.zap \
    pscanrulesBeta-beta-*.zap \
    && wget --quiet \
    https://github.com/zaproxy/zap-extensions/releases/download/ascanrules-v${ASCANRULES_VERSION}/ascanrules-release-${ASCANRULES_VERSION}.zap \
    https://github.com/zaproxy/zap-extensions/releases/download/ascanrulesBeta-v${ASCANRULESBETA_VERSION}/ascanrulesBeta-beta-${ASCANRULESBETA_VERSION}.zap \
    https://github.com/zaproxy/zap-extensions/releases/download/pscanrules-v${PSCANRULES_VERSION}/pscanrules-release-${PSCANRULES_VERSION}.zap \
    https://github.com/zaproxy/zap-extensions/releases/download/pscanrulesBeta-v${PSCANRULESBETA_VERSION}/pscanrulesBeta-beta-${PSCANRULESBETA_VERSION}.zap
# Autogenerated END

COPY --chown=zap:zap docker/teardown /zap/teardown
COPY --chown=zap:zap docker/zapw.sh /zap/zapw.sh

CMD ["/zap/zapw.sh"]
