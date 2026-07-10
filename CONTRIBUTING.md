# Contributing

To make contributions to this charm, you'll need a working
[development setup](https://documentation.ubuntu.com/juju/3.6/howto/manage-your-deployment/#set-up-your-deployment-local-testing-and-development).

Install the project dependencies with Poetry:

```shell
poetry install --all-groups
```

## Testing

This project uses `tox` for managing test environments. The main environments are:

```shell
tox run -e format              # format the source and tests
tox run -e lint                # run formatting checks, linting, codespell, and type checks
tox run -e unit                # run unit tests
tox run -e integration-charm   # run charm integration tests
```

Running `tox` without arguments runs the environments listed in `tox.ini`.

## Build the charm

Build the charm in this git repository using:

```shell
charmcraft pack
```
