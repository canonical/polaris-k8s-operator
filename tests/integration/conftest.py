# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from pathlib import Path
from platform import machine

import boto3.session
import jubilant
import pytest
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from .helpers import S3Info
from .supporting_charms import S3, Metastore, SingleVariantCharmVersion

load_dotenv()
logger = logging.getLogger(__name__)
logging.getLogger("jubilant.wait").setLevel(logging.WARNING)
BUCKET_NAME = "test-bucket"
PATH_NAME = "catalogs"


@pytest.fixture(scope="module")
def platform() -> str:
    """Fixture to provide the platform architecture for testing."""
    platforms = {
        "x86_64": "amd64",
        "aarch64": "arm64",
    }
    return platforms.get(machine(), "amd64")


@pytest.fixture(scope="module")
def polaris_charm(platform: str) -> Path:
    """Path to the packed polaris charm."""
    if not (path := next(iter(Path.cwd().glob(f"*-{platform}.charm")), None)):
        raise FileNotFoundError("Could not find packed polaris charm.")

    return path


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest, platform: str) -> Generator[jubilant.Juju, None, None]:
    keep_models = bool(request.config.getoption("--keep-models"))
    model = request.config.getoption("--model")

    if model is None:
        with jubilant.temp_model(keep=keep_models) as juju:
            juju.wait_timeout = 10 * 60
            juju.model_config({"update-status-hook-interval": "60s"})
            juju.model_constraints({"arch": platform})

            yield juju  # run the test

            if request.session.testsfailed:
                log = juju.debug_log(limit=30)
                print(log, end="")
    else:
        juju = jubilant.Juju()
        juju.model = model
        try:
            juju.status()
        except jubilant.CLIError:
            juju.add_model(model)

        juju.wait_timeout = 10 * 60
        juju.model_config({"update-status-hook-interval": "60s"})
        juju.model_constraints({"arch": platform})

        yield juju  # run the test

        if not keep_models:
            juju.destroy_model(model, destroy_storage=True, force=True)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--keep-models",
        action="store_true",
        default=False,
        help="keep temporarily-created models",
    )
    parser.addoption(
        "--model",
        action="store",
        help="Juju model to use; if not provided, a new temporary model "
        "will be created for each test module",
    )


@pytest.fixture(scope="module")
def metastore(platform: str) -> SingleVariantCharmVersion:
    return Metastore[platform]


@pytest.fixture(scope="module")
def s3(platform: str) -> SingleVariantCharmVersion:
    return S3[platform]


@pytest.fixture(scope="module")
def s3_credentials(request: pytest.FixtureRequest) -> Generator[S3Info, None, None]:
    keep_models = bool(request.config.getoption("--keep-models"))
    access_key = os.environ["S3_ACCESS_KEY"]
    secret_key = os.environ["S3_SECRET_KEY"]
    endpoint_url = os.environ["S3_SERVER_URL"]
    ca_bundle_path = os.environ.get("S3_CA_BUNDLE_PATH", "")

    session = boto3.session.Session(aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    s3 = session.resource(
        service_name="s3",
        endpoint_url=endpoint_url,
        verify=False,
        region_name="us-east-1",
        config=Config(
            connect_timeout=60,
            retries={"max_attempts": 4},
            request_checksum_calculation="when_supported",
            response_checksum_validation="when_supported",
            s3={"addressing_style": "path"},
        ),
    )
    test_bucket = s3.Bucket(BUCKET_NAME)

    # Delete test bucket if it exists
    if test_bucket in s3.buckets.all():
        logger.info(f"The bucket {BUCKET_NAME} already exists. Deleting it...")
        for obj in test_bucket.objects.all():
            # We need to iterate over keys because delete_objects (plural) has mandatory checksum
            obj.delete()
        test_bucket.delete()

    yield {
        "endpoint": endpoint_url,
        "access_key": access_key,
        "secret_key": secret_key,
        "bucket": BUCKET_NAME,
        "path": PATH_NAME,
        "ca_bundle_path": ca_bundle_path,
        "region": "us-east-1",
        "role_arn": os.environ.get("S3_ROLE_ARN", ""),
        "user_arn": os.environ.get("S3_USER_ARN", ""),
    }

    if not keep_models:
        logger.info("Tearing down test bucket...")
        try:
            for obj in test_bucket.objects.all():
                # Iterate over keys because delete_objects has a mandatory checksum.
                obj.delete()

            test_bucket.delete()
        except ClientError as e:
            logger.warning("Could not tear down test bucket: %s", e)
