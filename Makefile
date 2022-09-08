SHELL := /usr/bin/env bash
ZAP_VERSION = $(shell cat .zap-version)
DOCKER_OK := $(shell type -P docker)
ARTIFACTORY_FQDN ?= artefacts.tax.service.gov.uk

.PHONY: check_docker build authenticate_to_artifactory push_image prep_version_incrementor test clean help compose
.DEFAULT_GOAL := help

check_docker:
    ifeq ('$(DOCKER_OK)','')
	    $(error package 'docker' not found!)
    endif

build: check_docker prep_version_incrementor ## Build the docker image
	@echo '********** Building docker image ************'
	@prepare-release
	@docker build --build-arg ZAP_VERSION=$(ZAP_VERSION) --tag $(ARTIFACTORY_FQDN)/build-dynamic-application-security-testing:$$(cat .version) .

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

test: ## Run tests for additional scripts
	@$(MAKE) -C updater test

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'