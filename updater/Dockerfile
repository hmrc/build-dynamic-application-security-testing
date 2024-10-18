ARG PYTHON_VERSION

FROM python:${PYTHON_VERSION}-alpine AS pipenv
RUN apk add --no-cache shadow~=4.15.1-r0
# UID of current user who runs the build
ARG user_id
# GID of current user who runs the build
ARG group_id
# GID of current docker group of the host
ARG docker_group_id
# HOME of current user who runs the build
ARG home
# change GID for dialout group which collides with MacOS staff GID (20) and
# create group and user to match permmisions of current who runs the build
ARG workdir
WORKDIR ${workdir}
RUN groupmod -g 64 dialout \
    && addgroup -S \
    -g "${group_id}" \
    union \
    && groupmod -g 2999 ping \
    && mkdir -p "${home}" \
    && adduser -S \
    -u "${user_id}" \
    -h "${home}" \
    -s "/bin/bash" \
    -G union \
    builder \
    && if [ "${group_id}" -ne "${docker_group_id}" ]; then \
        addgroup -S \
            -g "${docker_group_id}" \
            docker \
        && gpasswd --add builder docker; \
    fi \
    && chown -R builder:union "${workdir}"
RUN apk add --no-cache \
    bash=~5.2.26-r0 \
    docker~=26.1.5-r0 \
    gcc~=13.2.1 \
    git~=2.45.2-r0 \
    musl-dev \
    make=~4.4.1 \
    && pip install --no-cache-dir --index-url https://artefacts.tax.service.gov.uk/artifactory/api/pypi/pips/simple pipenv==2024.1.0
USER builder
COPY --chown=builder:union Pipfile Pipfile.lock ./
RUN pipenv install --ignore-pipfile --dev
ENTRYPOINT [ "/usr/local/bin/pipenv" ]
