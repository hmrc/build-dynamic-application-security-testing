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