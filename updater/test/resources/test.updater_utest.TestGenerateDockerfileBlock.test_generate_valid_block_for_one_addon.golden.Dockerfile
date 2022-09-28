
WORKDIR /zap/plugin
ARG ASCANRULES_VERSION=36
RUN rm --force \
        ascanrules-release-*.zap \
    && wget --quiet \
        https://github.com/zaproxy/zap-extensions/releases/download/ascanrules-v${ASCANRULES_VERSION}/ascanrules-release-${ASCANRULES_VERSION}.zap
