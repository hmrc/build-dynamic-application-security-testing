DOCKER = docker run \
	--interactive \
	--rm \
	--env "PYTHONPATH=$(PYTHONPATH):updater/" \
	--env "GIT_API_PR_URL=$(GIT_API_PR_URL)" \
	--env "GIT_PR_URL=$(GIT_PR_URL)" \
	--env "GIT_FORK_URL=$(GIT_FORK_URL)" \
	--env "GIT_API_FORK_URL=$(GIT_API_FORK_URL)" \
	--env "GIT_HOST=$(GIT_HOST)" \
	--env "GIT_HMRC_USER=$(GIT_HMRC_USER)" \
	--env "GITHUB_API_USER=$(GITHUB_API_USER)" \
	--env "HOST_IP=$(HOST_IP)" \
	--env "MYPYPATH=${PWD}/typings" \
	--env "RETRY_DELAY=${RETRY_DELAY}" \
	--env "SLACK_HOST=$(SLACK_HOST)" \
	--env "SLACK_NOTIFICATION_URL=$(SLACK_NOTIFICATION_URL)" \
	--env "SLACK_USER=$(SLACK_USER)" \
	--env "SLACK_TOKEN=$(SLACK_TOKEN)" \
	--env "UPDATE_GOLDEN_FILES=$(UPDATE_GOLDEN_FILES)" \
	--env "ZAP_HOST=$(ZAP_HOST)" \
	--volume "$(PWD):${PWD}" \
	--volume "/var/run/docker.sock:/var/run/docker.sock" \
	--workdir "${PWD}"

SCANNERS_CONFIG ?= zap/configs/sm-frontend.json
ALERT_FILTERS_CONFIG ?= ./zap/configs/alert-filters.json

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -O globstar -c

OS := $(shell uname)

ifeq ($(OS), Darwin)
DOCKER_GROUP_ID = $(shell dscl . -read /Groups/staff | awk '($$1 == "PrimaryGroupID:") { print $$2 }')
endif

ifeq ($(OS), Linux)
DOCKER_GROUP_ID = $(shell getent group docker | cut -d: -f3)
endif

# HOST_IP regex explanation https://regex101.com/r/GOP2eB/2/f
HOST_IP ?= $(shell ifconfig \
	| grep -m 1 -oE "inet (10\.[0-9]+|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.[0-9]+\.[0-9]+" \
	| grep -oE "[0-9.]+")
GIT_HMRC_USER = hmrc
GITHUB_API_USER = zap24
GIT_PORT = 3000
GIT_HOST = $(HOST_IP):$(GIT_PORT)
GIT_FORK_URL = http://$(GIT_HOST)/$(GITHUB_API_USER)/build-dynamic-application-security-testing
GIT_PR_URL = http://$(GIT_HOST)/$(GIT_HMRC_USER)/build-dynamic-application-security-testing/pulls
GIT_API_URL = http://$(GIT_HOST)/api/v1/repos/$(GIT_HMRC_USER)/build-dynamic-application-security-testing
GIT_API_FORK_URL = $(GIT_API_URL)/forks
GIT_API_PR_URL = $(GIT_API_URL)/pulls
RETRY_DELAY = 0.01
SLACK_PORT = 8080
SLACK_HOST = $(HOST_IP):$(SLACK_PORT)
SLACK_NOTIFICATION_URL = http://$(SLACK_HOST)/slack-notifications/notification
SLACK_USER = a-slack-user
SLACK_TOKEN = super-secret
ZAP_PORT = 11000
ZAP_HOST = $(HOST_IP):$(ZAP_PORT)
ZAP_FAIL_ON_SEVERITY ?= Low

ZAP_LOCAL_SCANNER_CONFIG ?= sm-frontend.json
ZAP_LOCAL_ALERT_FILTERS ?= set-me-to-path-to-your-local-alert-filters.json

PYTHON_TEST_PATTERN ?= "*_?test.py" # Default to all types of tests
PYTHON_COVERAGE_MIN = 91 # %
PYTHON_VERSION := $(shell cat .python-version)

.PHONY: shfmt shellcheck pipenv docker-compose
shfmt shellcheck pipenv docker-compose:
	# building $@
	@docker build \
		--tag $@ \
		--build-arg PYTHON_VERSION=$(PYTHON_VERSION) \
		--build-arg "user_id=$(shell id -u)" \
		--build-arg "group_id=$(shell id -g)" \
		--build-arg "docker_group_id=$(DOCKER_GROUP_ID)" \
		--build-arg "home=${HOME}" \
		--build-arg "workdir=${PWD}" \
		--target $@ . \
		>/dev/null

.PHONY: fmt
fmt: shfmt pipenv
	@$(DOCKER) shfmt -l -w .
	@$(DOCKER) pipenv run black --line-length=120 .

.PHONY: fmt-check
fmt-check: shfmt pipenv md-check
	@$(DOCKER) shfmt -d .
	@$(DOCKER) pipenv run black --line-length=120 --check .

.PHONY: md-check
md-check:
	@docker pull zemanlx/remark-lint:latest >/dev/null
	@docker run --rm -i -v $(PWD):/lint/input:ro zemanlx/remark-lint --frail .

.PHONY: static-check
static-check: shellcheck pipenv
	@$(DOCKER) shellcheck $(shell git ls-files '/*.sh')
	@$(DOCKER) pipenv run flake8 --max-line-length=120 --max-complexity=10
	@$(DOCKER) pipenv run mypy --namespace-packages --strict ./**/*.py

.PHONY: coverage-check
coverage-check: python-coverage-only

.PHONY: test
test:
	@$(MAKE) python-unit-test
	@$(MAKE) python-integration-test
	#@$(MAKE) -C docker smoke-test
	#@$(MAKE) test-local-zap-settings

.PHONY: python-test
python-test: pipenv
	@$(DOCKER) pipenv run coverage run \
		--append \
		--branch \
		--omit "*_?test.py,*/.local/*" \
		--module unittest \
			discover \
			--verbose \
			--pattern $(PYTHON_TEST_FILE)$(PYTHON_TEST_PATTERN)

.PHONY: python-unit-test
python-unit-test:
	@$(MAKE) python-test PYTHON_TEST_PATTERN="*_utest.py" PYTHON_TEST_FILE=$(PYTHON_TEST_FILE)

.PHONY: python-integration-test
python-integration-test: setup-git-server start-slack-service-stub
	@$(MAKE) python-test PYTHON_TEST_PATTERN="*_itest.py" PYTHON_TEST_FILE=$(PYTHON_TEST_FILE)

.PHONY: python-coverage-only
python-coverage-only:
	@$(DOCKER) pipenv run coverage xml
	@$(DOCKER) pipenv run coverage report --fail-under $(PYTHON_COVERAGE_MIN)

.PHONY: python-coverage
python-coverage:
	-@rm .coverage
	@$(MAKE) python-unit-test
	@$(MAKE) python-integration-test
	@$(MAKE) python-coverage-only

.PHONY: python-test-update-golden-files
python-test-update-golden-files:
	UPDATE_GOLDEN_FILES=true $(MAKE) python-unit-test PYTHON_TEST_FILE=$(PYTHON_TEST_FILE)
	UPDATE_GOLDEN_FILES=true $(MAKE) python-integration-test PYTHON_TEST_FILE=$(PYTHON_TEST_FILE)

.PHONY: start-git-server
start-git-server: stop-git-server
	@docker run \
		--detach \
		--rm \
		--publish "$(GIT_PORT):$(GIT_PORT)" \
		--name gitea \
		gitea/gitea:1.12.5 \
		> /dev/null
	@while ! curl --silent http://$(GIT_HOST) >/dev/null; do sleep 0.1; done

.PHONY: setup-git-server
setup-git-server: start-git-server
	@curl 'http://$(GIT_HOST)/install' \
		--header 'Content-Type: application/x-www-form-urlencoded' \
		--data-raw 'db_type=SQLite3&charset=utf8&db_path=%2Fdata%2Fgitea%2Fgitea.db&app_name=Gitea&repo_root_path=%2Fdata%2Fgit%2Frepositories&run_user=git&domain=$(HOST_IP)&http_port=$(GIT_PORT)&app_url=http%3A%2F%2F$(HOST_IP)%3A$(GIT_PORT)%2F&log_root_path=%2Fdata%2Fgitea%2Flog' \
		--silent \
		> /dev/null
	@docker exec \
		--interactive \
		--user git \
		gitea gitea admin create-user \
			--email=$(GIT_HMRC_USER)@zap.org \
			--username=$(GIT_HMRC_USER) \
			--password=$(GIT_HMRC_USER) \
			--must-change-password=false \
		> /dev/null
	@docker exec \
		--interactive \
		--user git \
		gitea gitea admin create-user \
			--email=$(GITHUB_API_USER)@zap.org \
			--username=$(GITHUB_API_USER) \
			--password=$(GITHUB_API_USER) \
			--must-change-password=false \
		> /dev/null

.PHONY: stop-git-server
stop-git-server:
	@if [[ "$$( docker ps --filter name=gitea --quiet)" != "" ]]; then \
		docker stop gitea >/dev/null; \
	fi

.PHONY: build-slack-service-stub
build-slack-service-stub: stop-slack-service-stub
	@docker build \
		--tag slack-service-stub:latest \
		./test/wiremock \
		> /dev/null

.PHONY: start-slack-service-stub
start-slack-service-stub: build-slack-service-stub
	@docker run \
		-detach \
		--rm \
		--publish "$(SLACK_PORT):$(SLACK_PORT)" \
		--name slack-service-stub \
		slack-service-stub \
		> /dev/null

.PHONY: stop-slack-service-stub
stop-slack-service-stub:
	@if [[ "$$(docker ps --filter name=slack-service-stub --quiet)" != "" ]]; then \
		docker stop slack-service-stub >/dev/null; \
	fi

target:
	@mkdir -p target

# Simulates what is happening in DynamicApplicationSecurityTestingJobBuilder in
# Jenkins before acceptance tests are run
.PHONY: local-zap-running
local-zap-running: pipenv target
	@$(MAKE) -C docker restart ZAP_SAVE_SESSION=false
	@$(DOCKER) --env ZAP_HOST=$(ZAP_HOST) pipenv run python ./zap/client.py --wait-for-server 60
	@$(DOCKER) --env ZAP_HOST=$(ZAP_HOST) pipenv run python ./zap/client.py --reset-scanners "./zap/configs/$(ZAP_LOCAL_SCANNER_CONFIG)"
	@if [[ -f "$(ZAP_LOCAL_ALERT_FILTERS)" ]]; then \
		cp "$(ZAP_LOCAL_ALERT_FILTERS)" ./target/alert-filters.json; \
		$(DOCKER) --env ZAP_HOST=$(ZAP_HOST) pipenv run python ./zap/client.py --manage-alerts ./target/alert-filters.json; \
	fi

# Simulates what is happening in DynamicApplicationSecurityTestingJobBuilder in
# Jenkins after acceptance tests are run
.PHONY: local-zap-stop
local-zap-stop: pipenv
	@$(DOCKER) --env ZAP_HOST=$(ZAP_HOST) pipenv run python ./zap/client.py --log-proxied-urls
	@$(DOCKER) --env ZAP_HOST=$(ZAP_HOST) pipenv run python ./zap/client.py --wait-for-report 300 1
	@$(DOCKER) --env ZAP_HOST=$(ZAP_HOST) pipenv run python ./zap/client.py --generate-report
	@$(DOCKER) --env ZAP_HOST=$(ZAP_HOST) pipenv run ./zap/client.py --determine-result --fail-on "$(ZAP_FAIL_ON_SEVERITY)" \
		|| ($(MAKE) -C docker stop && echo  "FAIL: There are findings above $(ZAP_FAIL_ON_SEVERITY) level" && exit 13)
	@$(MAKE) -C docker stop

.PHONY: test-local-zap-settings
test-local-zap-settings:
	$(MAKE) start-git-server
	@rm -rf ./target
	$(MAKE) local-zap-running \
		ZAP_FORWARD_ENABLE=true \
		ZAP_FORWARD_PORTS=$(GIT_PORT) \
		ZAP_LOCAL_SCANNER_CONFIG=sm-api.json \
		ZAP_LOCAL_ALERT_FILTERS="${PWD}/test/fixtures/alert-filters.json"

	@# scanner 10003 is not enabled for API scan
	@echo -en "Selected scanner config is used: "
	@curl --silent "http://localhost:$(ZAP_PORT)/JSON/pscan/view/scanners/" \
		| jq --exit-status '.scanners[] | select(.id=="10003") | .enabled == "false"'

	@# scanner 10021 is set to -1 using alert-filters from test fixtures
	@echo -en "Alert filters are applied: "
	@curl --silent "http://localhost:$(ZAP_PORT)/JSON/alertFilter/view/globalAlertFilterList/?contextId=1" \
		| jq --exit-status '.globalAlertFilterList[] | select(.ruleId=="10021") | .newLevel == "-1"'

	@echo -e "\nIf forwarding is not working curl will get 502 Bad Gateway and fails."
	@curl --fail --proxy "http://localhost:$(ZAP_PORT)" "localhost:$(GIT_PORT)" >/dev/null

	$(MAKE) local-zap-stop ZAP_FAIL_ON_SEVERITY=High
	$(MAKE) stop-git-server

	@echo -en "Session file exists: "
	@test -f target/session/1.session && echo "OK"

	@echo -en "Session archive exists: "
	@test ! -e target/session/1.tar.xz  && echo "OK"

	@echo -en "DAST report exists: "
	@test -f target/dast-reports/index.html && echo "OK"

	@echo -en "Proxied URLs report exists: "
	@test -f target/dast-reports/proxied_urls.log && echo "OK"

.PHONY: start-metrics-service
start-metrics-service: docker-compose
	@$(DOCKER) docker-compose \
		--file test/metrics/docker-compose.yml \
		up \
		--force-recreate \
		--detach

.PHONY: stop-metrics-service
stop-metrics-service: docker-compose
	@$(DOCKER) docker-compose \
		--file test/metrics/docker-compose.yml \
		down
