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
MANAGEMENT_PORT = 8182
REALM = "POLARIS"

# Configuration files
POLARIS_APPLICATION_PROPERTIES = "/etc/polaris/application.properties"
SYMMETRIC_KEY = "/etc/polaris/symmetric.key"

# Relation names
PEERS_RELATION_NAME = "polaris-peers"
STATUS_RELATION_NAME = "status-peers"

# Misc.
ADMIN_USER = "charmed-operator"
SYSTEM_USER_SECRET_LABEL_SUFFIX = "system_user_secret"
RANDOM_KEY_SIZE = 32
