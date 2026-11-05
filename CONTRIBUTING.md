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

## Charm structure

### Containers

This charm uses a total a three containers during its runtime:

- The charm code runs in its own container
- Apache Polaris run in the `polaris` container ([rock repository](https://github.com/canonical/charmed-polaris-rock))
- The `console` container runs nginx to serve the Polaris Console UI ([rock repository](https://github.com/canonical/polaris-console-rock/))

This structure was motivated by our opinionated approach to creating an operator for Apache Polaris:

- by having the `console` container part of the charm, we save ourselves the trouble of creating a different charm designing what the integration between the service and the console charms should look like
- the charm as complete control over both workloads, meaning that we can simplify the integration with other charms. For instance, the integration with the Identity platform is aware of the ingress integration for the redirect URL
- the nginx instance in the `console` container not only serves the Polaris console but also acts as a reverse proxy to Polaris. We can use this to terminate TLS at the ingress, leaving the charm free to interact with Polaris without having to deal with TLS

### Code structure

This repository follows the "charm pattern" commonly found in Data Platform and Analytics code bases.
This convention defines at least three tiers:

- Event handlers (under `src/events/`) registers the actual Juju events the charm is reacting to at the granularity of our choosing. It is usually set to a per-domain segmentation: for instance we have `events/s3.py` handling all the events related to the integration with the `s3-integration`, but a new event handler could really be about anything. They also handle the databag writes and the charm statuses.
- Managers (under `src/managers`) contains the actual logic for each domain. For instance, `managers/tls.py` contains the logic to build a certificate signing request for the integration with a certificate provider charm.
- Workloads (under `src/core/workloads`) take care of managing the containers state: writing configuration file, updating pebble layers and restarting the services.

In addition, the charm pattern also commonly use a state context, created in `src/charm.py` and passed as a parameter to all event handlers.

The Polaris K8s charm has an opinionated approach to the holistic state reconciliation recommended for charms.
In a nutshell, each event handlers acts as a logical sub charm, reconciling the charm's current state with its expected state.
We found this approach to be quite beneficial in having the best of both worlds: the robustness of the holistic approach with the maintainability of single purposed event handlers.
It is even possible to trigger another event handler reconcile method for complex chained relations: for instance, integrating with a certificate provider triggers a change to the `ingress` relation (changing the port to be exposed), triggering an update on the `oauth` relation (changing the redirect URL scheme).
