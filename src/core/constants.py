# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#
"""List constants used throughout the charm code base."""

# Containers and services
POLARIS_CONTAINER_NAME = "polaris"
POLARIS_SERVICE_NAME = "polaris"

POLARIS_GROUP = "_daemon_"
POLARIS_USER = "_daemon_"

REST_PORT = 8181
REALM = "POLARIS"

# Files
POLARIS_APPLICATION_PROPERTIES = "/etc/polaris/application.properties"
SYMMETRIC_KEY = "/etc/polaris/symmetric.key"
ROCK_METADATA = "/.rock/metadata.yaml"

# Relation names
PEERS_RELATION_NAME = "polaris-peers"
STATUS_RELATION_NAME = "status-peers"
METASTORE_RELATION_NAME = "metastore"

# Misc.
ADMIN_USER = "charmed-operator"
POLARIS_METASTORE_DATABASE_NAME = "polaris"
POLARIS_BOOTSTRAP_COMMAND = ("/opt/polaris/bin/admin", "bootstrap")
SYSTEM_USER_SECRET_LABEL_SUFFIX = "system_user_secret"
RANDOM_KEY_SIZE = 32
