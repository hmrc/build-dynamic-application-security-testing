# Contributing

Running the updater python script will fail without proper github user configuration.  When running locally, use `--no-publish` to avoid this step.
```
./updater.py --no-publish
```

Before you push your changes please format files with

```bash
make fmt
```

run all available tests

```bash
make test
```

check that the code has sufficient test coverage

```bash
make coverage-check
```

All python unit tests with fixtures in `resources` folder support updating
*golden* files from real output of tests

```bash
make python-test-update-golden-files
```

this is useful if you have made changes in code and you do not want to update
all fixtures manually or when you have updated inputs and therefore fixtures
needs to be updated.

## Troubleshooting PR-builder failures

If the updater image fails to build with `ERROR: unable to select packages`,
check the package versions in `updater/Dockerfile`. For example, the build
requested Docker `29.8.2-r0`, but Alpine only offered `29.9.2-r0`, so the
tests could not start. This was a build dependency issue, not a ZAP add-on issue.

If this happens again, update the affected package's version restriction in
`updater/Dockerfile` to a compatible version available from Alpine. From the
`updater` directory, run `make pipenv` to check the image builds, then `make test`
to run the updater tests.

## Deployment steps

After the PR builder succeeds and the PR has been approved and merged:

1. Monitor the [DAST-canary-experimental](https://build.tax.service.gov.uk/job/PlatOps/job/Services/job/DAST-canary-experimental/) build job.
2. Compare its generated report with the last report from
   [DAST-canary-latest](https://build.tax.service.gov.uk/job/PlatOps/job/Services/job/DAST-canary-latest/). Review any changes in alerts and check
   for scan errors.
3. If you are happy with the changes, manually trigger the
   [DAST-canary-latest](https://build.tax.service.gov.uk/job/PlatOps/job/Services/job/DAST-canary-latest/) build job using **Build with Parameters** to pick up the latest changes.
