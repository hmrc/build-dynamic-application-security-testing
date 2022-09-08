WORKDIR /zap/plugin
ARG ASCANRULES_VERSION=36
ARG ASCANRULESBETA_VERSION=31
ARG PSCANRULES_VERSION=29
ARG PSCANRULESBETA_VERSION=22
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
