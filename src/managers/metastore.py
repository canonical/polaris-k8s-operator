# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Metastore manager."""

import psycopg
from psycopg import sql

from core.constants import POLARIS_METASTORE_SCHEMA
from core.context import Context
from core.logging import WithLogging


class MetastoreManager(WithLogging):
    """Metastore manager."""

    def __init__(self, context: Context) -> None:
        self.context = context

    def ensure_schema(self) -> bool:
        """Ensure schema is present in the database.

        Polaris 1.8.0 requires the schema to exist before we bootstrap.
        """
        if not (metastore := self.context.metastore).ready:
            return False

        query = sql.SQL("CREATE SCHEMA IF NOT EXISTS {schema}").format(
            schema=sql.Identifier(POLARIS_METASTORE_SCHEMA),
            owner=sql.Identifier(metastore.username),
        )

        host, _, port = metastore.endpoint.partition(":")

        try:
            with psycopg.connect(
                host=host,
                port=port or 5432,
                dbname=metastore.database,
                user=metastore.username,
                password=metastore.password,
            ) as conn:
                conn.execute(query)

        except psycopg.Error:
            self.logger.exception(f"Failed to create schema '{POLARIS_METASTORE_SCHEMA}'")
            return False

        return True
