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
MONITORING_PORT = 8182
REALM = "POLARIS"

# Files
POLARIS_APPLICATION_PROPERTIES = "/etc/polaris/application.properties"
OBJECT_STORAGE_CERTIFICATE = "/etc/polaris/object-storage-ca.pem"
OBJECT_STORAGE_TRUSTSTORE = "/etc/polaris/object-storage-truststore.jks"
SYMMETRIC_KEY = "/etc/polaris/symmetric.key"
ROCK_METADATA = "/.rock/metadata.yaml"

# Relation names
METASTORE_RELATION_NAME = "metastore"
PEERS_RELATION_NAME = "polaris-peers"
S3_RELATION_NAME = "s3-credentials"
STATUS_RELATION_NAME = "status-peers"

# Misc.
ADMIN_USER = "charmed-operator"
POLARIS_METASTORE_DATABASE_NAME = "polaris"
OBJECT_STORAGE_CA_ALIAS = "object-storage-ca"
POLARIS_BOOTSTRAP_COMMAND = ("/opt/polaris/bin/admin", "bootstrap")
KEYTOOL = "keytool"
SYSTEM_USER_SECRET_LABEL_SUFFIX = "system_user_secret"
RANDOM_KEY_SIZE = 32
