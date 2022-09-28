
WORKDIR /zap/plugin
ARG ASCANRULES_VERSION=36
ARG ASCANRULESBETA_VERSION=30
RUN rm --force \
        ascanrules-release-*.zap \
        ascanrulesBeta-beta-*.zap \
    && wget --quiet \
        https://github.com/zaproxy/zap-extensions/releases/download/ascanrules-v${ASCANRULES_VERSION}/ascanrules-release-${ASCANRULES_VERSION}.zap \
        https://github.com/zaproxy/zap-extensions/releases/download/ascanrulesBeta-v${ASCANRULESBETA_VERSION}/ascanrulesBeta-beta-${ASCANRULESBETA_VERSION}.zap
