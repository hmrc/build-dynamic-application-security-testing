SHELL := /usr/bin/env bash
ZAP_VERSION = $(shell cat .zap-version)
DOCKER_OK := $(shell type -P docker)
ARTIFACTORY_FQDN ?= artefacts.tax.service.gov.uk

# local smoke test configuration
ZAP_CONTAINER_NAME = zap
ZAP_FORWARD_ENABLE ?= false
ZAP_FORWARD_PORTS ?= 8000 8001
ZAP_BUILD_NUMBER = 1
ZAP_JOB_BASE_NAME = bash-test
ZAP_PORT ?= 11000
ZAP_HOST ?= localhost:$(ZAP_PORT)
ZAP_SAVE_SESSION ?= true
ZAP_STORAGE_SESSIONS_HOST = httpbin.org/anything
ZAP_STORAGE_SESSIONS_API_KEY = APIKeyExampleTxcYRDgKEpu2vcYyT
ZAP_HOME = /home/zap/.ZAP
ZAP_IMAGE_LOCAL_TAG = build-dynamic-application-security-testing:local
TEST_WAIT_THRESHOLD = 60
PARENT_DIR := $(shell dirname ${PWD})
HOST_IP ?= $(shell ifconfig \
	| grep -m 1 -oE "inet (10\.[0-9]+|172\.(1[6-9]|2[0-9]|3[01])|192\.168)\.[0-9]+\.[0-9]+" \
	| grep -oE "[0-9.]+") # HOST_IP regex explanation https://regex101.com/r/GOP2eB/2/

.PHONY: check_docker build authenticate_to_artifactory push_image prep_version_incrementor test clean help compose
.DEFAULT_GOAL := help

check_docker:
    ifeq ('$(DOCKER_OK)','')
	    $(error package 'docker' not found!)
    endif

build: check_docker prep_version_incrementor ## Build the docker image
	@echo '********** Building docker image ************'
	@prepare-release
	@docker buildx build --platform linux/arm64,linux/amd64 --build-arg ZAP_VERSION=$(ZAP_VERSION) --tag $(ARTIFACTORY_FQDN)/build-dynamic-application-security-testing:$$(cat .version) .

authenticate_to_artifactory:
	@docker login --username ${ARTIFACTORY_USERNAME} --password "${ARTIFACTORY_PASSWORD}" $(ARTIFACTORY_FQDN)

push_image: ## Push the docker image to artifactory
	@docker push $(ARTIFACTORY_FQDN)/build-dynamic-application-security-testing:$$(cat .version)
	@cut-release

push_latest: ## Push the latest tag to artifactory
	@docker tag $(ARTIFACTORY_FQDN)/build-dynamic-application-security-testing:$$(cat .version) $(ARTIFACTORY_FQDN)/build-dynamic-application-security-testing:latest
	@docker push $(ARTIFACTORY_FQDN)/build-dynamic-application-security-testing:latest

prep_version_incrementor:
	@echo "Installing version-incrementor"
	@pip install -i https://$(ARTIFACTORY_FQDN)/artifactory/api/pypi/pips/simple 'version-incrementor<2'

clean: ## Remove the docker image
	@echo '********** Cleaning up ************'
	@docker rmi -f $$(docker images $(ARTIFACTORY_FQDN)/build-dynamic-application-security-testing:$$(cat .version) -q)

test: ## Run tests
	@$(MAKE) -C updater test
	@$(MAKE) smoke-test

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: smoke-test
smoke-test: start
	@$(MAKE) stop
	@if [[ $$(docker inspect $(ZAP_CONTAINER_NAME) --format='{{.State.ExitCode}}') -ne 0 ]]; then \
		docker logs $(ZAP_CONTAINER_NAME); \
		exit 1; \
	fi

.PHONY: start
start: build-local session-dir
	@echo -n "Removing old $(ZAP_CONTAINER_NAME) container: "
	-@docker stop $(ZAP_CONTAINER_NAME) >/dev/null
	-@docker rm $(ZAP_CONTAINER_NAME) >/dev/null && echo "Done"
	@echo -n "Starting Docker container: "
	@docker run \
		--user zap \
		--env "HOST_IP=$(HOST_IP)" \
		--env "ZAP_FORWARD_ENABLE=$(ZAP_FORWARD_ENABLE)" \
		--env "ZAP_FORWARD_PORTS=$(ZAP_FORWARD_PORTS)" \
		--env "ZAP_BUILD_NUMBER=$(ZAP_BUILD_NUMBER)" \
		--env "ZAP_JOB_BASE_NAME=$(ZAP_JOB_BASE_NAME)" \
		--env "ZAP_PORT=$(ZAP_PORT)" \
		--env "ZAP_SAVE_SESSION=$(ZAP_SAVE_SESSION)" \
		--env "ZAP_STORAGE_SESSIONS_HOST=$(ZAP_STORAGE_SESSIONS_HOST)" \
		--env "ZAP_STORAGE_SESSIONS_API_KEY=$(ZAP_STORAGE_SESSIONS_API_KEY)" \
		--volume "$(PARENT_DIR)/target/session:$(ZAP_HOME)/session" \
		--detach \
		--publish "$(ZAP_PORT):$(ZAP_PORT)" \
		--name $(ZAP_CONTAINER_NAME) \
		$(ZAP_IMAGE_LOCAL_TAG) \
	>/dev/null \
	&& echo "Done"
	@echo -n "Waiting for ZAP API to be online: "
	@for i in {1..$(TEST_WAIT_THRESHOLD)}; do \
		if curl --fail --silent "http://$(ZAP_HOST)/JSON/core/view/version/?" >/dev/null; then \
			break; \
		fi; \
		if [[ $${i} -eq $(TEST_WAIT_THRESHOLD) ]]; then \
			echo -e "Fail\nCannot get response from ZAP API for $(TEST_WAIT_THRESHOLD) seconds."; \
			echo "Inspect following docker logs:"; \
			docker logs $(ZAP_CONTAINER_NAME); \
			exit 1; \
		fi; \
		sleep 1; \
		echo -n "."; \
	done
	@echo -e " Done\nZAP is listening on http://$(ZAP_HOST)"

.PHONY: build-local
build-local:
	@docker build \
		--quiet \
		--build-arg ZAP_VERSION=$(ZAP_VERSION) \
		--tag $(ZAP_IMAGE_LOCAL_TAG) \
		--file Dockerfile \
		. >/dev/null

.PHONY: session-dir
session-dir:
	@rm -rf "$(PARENT_DIR)/target/session"
	@mkdir -p "$(PARENT_DIR)/target/session"
	@chmod 777 "$(PARENT_DIR)/target/session"

.PHONY: stop
stop:
	@echo -n "Stopping via API call: "
	-@curl --fail "http://$(ZAP_HOST)/JSON/core/action/shutdown/"
	@echo -en "\nWaiting for Docker container to stop: "
	@for i in {1..$(TEST_WAIT_THRESHOLD)}; do \
		if [[ -z "$$(docker ps --quiet --filter "name=$(ZAP_CONTAINER_NAME)")" ]]; then \
			break; \
		fi; \
		if [[ $${i} -eq $(TEST_WAIT_THRESHOLD) ]]; then \
			echo -e "Fail\nCannot stop ZAP server for $(TEST_WAIT_THRESHOLD) seconds."; \
			echo "Inspect following docker logs:"; \
			docker logs $(ZAP_CONTAINER_NAME); \
			exit 13; \
		fi; \
		sleep 1; \
		echo -n "."; \
	done
	@echo " Done"
