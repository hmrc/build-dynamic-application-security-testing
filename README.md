# build-dynamic-application-security-testing

This repository is responsible for the docker image used by the DAST build jobs.

There are 3 Docker images available:
- `experimental` : mirrors the main branch with most recent changes
- `latest` : a stable version used by the DAST jobs
- `n.n.n` : corresponding to the semver version number for each commit

Unless stated otherwise, all DAST build jobs run against the `latest` tag of this image.

## ZAP add-ons
The ZAP proxy runs with a versioned set of *addons* enabled. The list of currently
supported addons is in the updaters [zap_addons](updater/zap_addons) file.

### Automatic updates
There is a python script that can be used to check for updates against the zap add-ons defined.

A jenkins job has been configured to trigger this daily.

If updates are available, the job will folk the repository, apply the updates to the Dockerfile and raise a PR.

## Making changes
See [updater README](updater/README.md) for more guidance on making changes to the updater.

The image itself has a smoke test that proves the image can be successfully started and stopped in docker.

Running the updater tests and image smoke test can be done from the root directory with: 
```
make test
```

### Updating ZAP
To change the version of zap used, simply update the [zap version](.zap-version) file in the root directory. 

## Release process
When a PR is merged, the *build-dynamic-application-security-testing-docker-image* build job will:
 * Bump the semver version number
 * Create a new image
 * Tag the image with both the new version number and `experimental`
 * Publish the images to artifactory
 * Trigger the *DAST-canary-experimental* job to test the new image

If the *DAST-canary-experimental* build passes, the image can then be promoted to `latest` by building [promote-artifactory-docker-tag](https://build.tax.service.gov.uk/job/build-and-deploy/job/promote-artifactory-docker-tag/) with the following parameters:

- IMAGE_NAME: build-dynamic-application-security-testing
- SOURCE_TAG: the semver of the [latest release](https://github.com/hmrc/build-dynamic-application-security-testing/releases/latest)
- DESTINATION_TAG (auto-populated): latest

### Versioning
The build job uses the *version incrementor* to increment the semver version number.  By default, the minor version will be incremented by 1 on every commit.

To create a new major release, simply update the [major version](.major-version) file in the root directory. 

## Usage
For guidance on how to interact with this docker image, please follow the steps outlined by the [dast-config-manager](https://github.com/hmrc/dast-config-manager).

### License

This code is open source software licensed under the [Apache 2.0 License](http://www.apache.org/licenses/LICENSE-2.0.html).