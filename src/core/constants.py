# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
#
"""List constants used throughout the charm code base."""

# Containers and services
POLARIS_CONTAINER_NAME = "polaris"
POLARIS_SERVICE_NAME = "polaris"

CONSOLE_CONTAINER_NAME = "console"
CONSOLE_SERVICE_NAME = "nginx"

WORKLOAD_GROUP = "_daemon_"
WORKLOAD_USER = "_daemon_"

CONSOLE_PORT = 8080
CONSOLE_TLS_PORT = 8443
REST_PORT = 8181
MONITORING_PORT = 8182
REALM = "POLARIS"

# Files
POLARIS_APPLICATION_PROPERTIES = "/etc/polaris/application.properties"
OBJECT_STORAGE_CERTIFICATE = "/etc/polaris/object-storage-ca.pem"
ADDITIONAL_CA_CERTIFICATE = "/etc/polaris/additional-ca.pem"
POLARIS_TRUSTSTORE = "/etc/polaris/polaris-truststore.jks"
DEFAULT_JAVA_TRUSTSTORE = "/etc/ssl/certs/java/cacerts"
SYMMETRIC_KEY = "/etc/polaris/symmetric.key"
ROCK_METADATA = "/.rock/metadata.yaml"
CONSOLE_TLS_CERTIFICATE = "/etc/nginx/tls/tls.crt"
CONSOLE_TLS_PRIVATE_KEY = "/etc/nginx/tls/tls.key"

# Relation names
METASTORE_RELATION_NAME = "metastore"
OAUTH_RELATION_NAME = "oauth"
RECEIVE_CERTS_RELATION_NAME = "receive-ca-certs"
PEERS_RELATION_NAME = "polaris-peers"
S3_RELATION_NAME = "s3-credentials"
STATUS_RELATION_NAME = "status-peers"
TLS_RELATION_NAME = "client-certificates"

# Misc.
ROOT_PRINCIPAL_ID = "charmed-operator"
POLARIS_METASTORE_DATABASE_NAME = "polaris"
POLARIS_BOOTSTRAP_COMMAND = ("/opt/polaris/bin/admin", "bootstrap")
KEYTOOL = "keytool"
DEFAULT_JAVA_TRUSTSTORE_PASSWORD = "changeit"
SYSTEM_USER_SECRET_LABEL_SUFFIX = "system_user_secret"
RANDOM_KEY_SIZE = 32
OAUTH_CALLBACK_PATH = "/login"
