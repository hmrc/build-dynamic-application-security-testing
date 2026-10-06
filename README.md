# build-dynamic-application-security-testing

This repository is responsible for the docker image used by the DAST build jobs.

There are 3 Docker images available:
- `experimental` : mirrors the main branch with most recent changes
- `latest` : a stable version used by the DAST jobs
- `n.n.n` : corresponding to the semver version number for each commit

Unless stated otherwise, all DAST build jobs run against the `latest` tag of this image.

## Making changes

### Updating ZAP and its add-ons
The ZAP proxy runs with a versioned set of *add-ons* enabled. The list of
supported add-ons is in [updater/zap_addons](updater/zap_addons).

To change the version of ZAP used, update the [ZAP version](.zap-version) file
in the repository root. After changing `.zap-version`, manually run the
following command so that the Dockerfile contains add-on versions compatible
with the new ZAP version:

```bash 
docker run --rm \
  --interactive \
  --volume "$PWD/..:$PWD/.." \
  --workdir "$PWD" \
  pipenv \
  run python updater.py --no-publish
```

The repository root also contains a [.python-version](.python-version) file.
It is not read by the updater Python code, but the updater `Makefile` uses it
when selecting the Python Docker image for tests. If the supported Python
version changes, update `.python-version` in the repository root and update
`updater/Pipfile` and `updater/Pipfile.lock` if the updater dependency
environment changes.

### Automatic add-on updates
The updater can check for updates to the ZAP add-ons defined in
`updater/zap_addons`. A Jenkins job runs this check daily. If updates are
available, it forks the repository, applies the updates to the Dockerfile,
and raises a pull request. Manual review and merging are still required;
check the [alerts Slack channel](https://grid-hmrcdigital.enterprise.slack.com/archives/CFCAB3RRN)
for these notifications.

### Making changes to the updater
See [updater README](updater/README.md) for more guidance on making changes to the updater.

The updater tests and image smoke test can be run from the repository root:

```bash
make test
```

The image smoke test verifies that the image can be successfully started and
stopped in Docker.

### Local DAST smoke test
Before relying on the `DAST-canary-experimental` job, the local image and the
DAST sidecar lifecycle can be checked with:

```bash
./build-dynamic-application-security-testing/scripts/run-local-dast-smoke.sh
```

The script expects these three repositories to be siblings under one parent
directory:

```text
parent-directory/
├── build-dynamic-application-security-testing/
├── dast-config-manager/
└── build-jobs/
```

When run from `parent-directory`, no option is needed. The script uses the
current directory as the parent, checks that the DAST repository is present,
and clones `dast-config-manager` and `build-jobs` from GitHub into the parent
if either is missing. Existing directories are left unchanged.

If you run the script from another location, such as the
`build-dynamic-application-security-testing/scripts` directory, specify the
parent explicitly:

```bash
./run-local-dast-smoke.sh --parent-dir /path/to/parent-directory
```

The script builds and starts the local image, checks the ZAP API and passive
scanners, sends a request through ZAP, configures the scanners through
`dast-config-manager`, generates a report, evaluates the result, and shuts ZAP
down. If the sidecar's Compose build image is unavailable from the internal
registry, the script downloads `docker/compose:1.29.2` and tags it with the
name expected by the sidecar.

If your current directory is not the parent directory containing the three
repositories, pass that parent directory with `--parent-dir`. Add
`--verbose` to print full Docker, ZAP, and sidecar output:

```bash
./build-dynamic-application-security-testing/scripts/run-local-dast-smoke.sh \
  --parent-dir /path/to/parent \
  --verbose
```

Startup, dependency, or lifecycle errors cause the script to fail. Findings
returned by the synthetic smoke request are reported as warnings after the
report has completed. Set `SMOKE_TARGET_URL` to test a reachable local or
development target instead of the default `http://example.com/`.

## Release process
When a PR is merged, the *build-dynamic-application-security-testing-docker-image* build job will:
 * Bump the semver version number
 * Create a new image
 * Tag the image with both the new version number and `experimental`
 * Publish the images to artifactory
 * Trigger the *DAST-canary-experimental* job to test the new image

### Testing before promotion

Run acceptance tests through *DAST-canary-experimental* using the `experimental`
image. Keep `latest` pointing to the current approved image while testing, so
changes can be validated without affecting users of the normal DAST jobs.

**A passing Jenkins build is not enough: open the generated Security Assessment
HTML report and check it for ZAP errors.** During the Python/ZAP upgrade, errors
were found in the HTML report itself rather than surfaced as build failures.

Before promoting an image:

- Inspect the HTML report for ZAP error messages, exceptions, and missing or
  incomplete scan results. A report showing no security alerts is not evidence
  of a successful scan if it also contains errors.
- Check that the reported findings agree with the Jenkins security result.
  Investigate cases where Jenkins counts High, Medium, or Low findings but the
  HTML report shows none. The HTML summary groups alert types, while the API
  summary counts instances, so non-zero totals are not necessarily identical.
- Compare the logs and scan duration with a previous successful canary run.
  Investigate new errors or unexpected slowdowns before promotion.

### Promoting to latest

Once the experimental tests and report checks pass, record the semver image
currently elected as `latest` so it can be restored if needed. Promote the tested
image by building [promote-artifactory-docker-tag](https://build.tax.service.gov.uk/job/build-and-deploy/job/promote-artifactory-docker-tag/) with the following parameters:

- IMAGE_NAME: build-dynamic-application-security-testing
- SOURCE_TAG: the exact semver image validated by the experimental tests
- DESTINATION_TAG (auto-populated): latest

### Rollback

If an issue is found after promotion, **run the promotion pipeline to elect the
last known-good image as `latest`**:

1. Open [promote-artifactory-docker-tag](https://build.tax.service.gov.uk/job/build-and-deploy/job/promote-artifactory-docker-tag/).
2. Set `IMAGE_NAME` to `build-dynamic-application-security-testing`.
3. Set `SOURCE_TAG` to the known-good semver recorded before promotion.
4. Set `DESTINATION_TAG` to `latest` and run the pipeline.
5. Rerun an affected DAST job, verify it uses the restored image, and check both
   its Jenkins result and generated HTML report for the original issue.

If the issue is found while testing `experimental`, leave `latest` on the
approved image and fix and retest the experimental image before promotion.

### Versioning
The build job uses the *version incrementor* to increment the semver version number.  By default, the minor version will be incremented by 1 on every commit.

To create a new major release, simply update the [major version](.major-version) file in the root directory. 

## Usage
For guidance on how to interact with this docker image, please follow the steps outlined by the [dast-config-manager](https://github.com/hmrc/dast-config-manager).

### License

This code is open source software licensed under the [Apache 2.0 License](http://www.apache.org/licenses/LICENSE-2.0.html).
