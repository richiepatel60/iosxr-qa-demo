"""Shared pytest fixtures for the IOS-XR manageability suite.

Fixtures live here (rather than in each test file) so that every test module
under ``tests/`` can request the same live NETCONF session or RESTCONF client
through pytest's dependency injection. Session-scoped fixtures mean the
(relatively expensive) transports are opened only once per test run.
"""

from __future__ import annotations

import logging
import socket

import pytest
from ncclient import manager
from ncclient.transport.errors import AuthenticationError, SSHError

import config

log = logging.getLogger("iosxr-qa")


@pytest.fixture(scope="session")
def netconf_session():
    """Open one NETCONF session (over SSH, TCP/830) shared by the whole run.

    Everything before ``yield`` is setup; everything after is teardown, so the
    session is always closed cleanly even if a test fails.
    """
    try:
        session = manager.connect(
            host=config.HOST,
            port=config.NETCONF_PORT,
            username=config.USERNAME,
            password=config.PASSWORD,
            hostkey_verify=False,   # lab box: do not verify the SSH host key
            look_for_keys=False,    # force password auth, ignore local SSH keys
            allow_agent=False,
            timeout=config.TIMEOUT,
            device_params={"name": "iosxr"},  # ncclient IOS-XR handling
        )
    except AuthenticationError:
        pytest.fail(
            f"NETCONF authentication failed for "
            f"{config.USERNAME}@{config.HOST}:{config.NETCONF_PORT} - "
            f"check XR_USERNAME / XR_PASSWORD."
        )
    except SSHError as exc:
        pytest.fail(
            f"Could not open a NETCONF/SSH transport to "
            f"{config.HOST}:{config.NETCONF_PORT} - {exc}. "
            f"Is 'netconf-yang agent ssh' enabled and the router reachable?"
        )

    assert session is not None  # connect() raised above otherwise
    log.info("NETCONF session %s established to %s", session.session_id, config.HOST)
    yield session

    if session.connected:
        session.close_session()
        log.info("NETCONF session closed cleanly")


@pytest.fixture(scope="session")
def restconf():
    """Return a ``(requests.Session, base_url)`` pair for RESTCONF calls.

    RESTCONF is not exposed on every IOS-XR image. If the agent is not reachable
    the RESTCONF tests are *skipped* (not failed), so the suite stays meaningful
    on NETCONF-only platforms.
    """
    import requests
    import urllib3
    from requests.auth import HTTPBasicAuth

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    base_url = f"https://{config.HOST}:{config.RESTCONF_PORT}/restconf"
    session = requests.Session()
    session.auth = HTTPBasicAuth(config.USERNAME, config.PASSWORD)
    session.headers.update({"Accept": "application/yang-data+json"})
    session.verify = False  # lab box: self-signed certificate

    try:
        session.get(
            f"{base_url}/data/ietf-yang-library:modules-state",
            timeout=config.TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        session.close()
        pytest.skip(
            f"RESTCONF not reachable on {config.HOST}:{config.RESTCONF_PORT} "
            f"({exc}) - enable it on the router to run these tests."
        )

    yield session, base_url
    session.close()


@pytest.fixture(scope="session")
def gnmi_target():
    """Return connection kwargs for a pygnmi ``gNMIclient``.

    gNMI runs over gRPC (default TCP/57400 on IOS-XR) and is the platform's
    native model-driven / streaming-telemetry interface. If gRPC is not
    reachable the gNMI tests are *skipped* rather than failed, matching the
    RESTCONF fixture's capability-aware behaviour.
    """
    host, port = config.HOST, config.GNMI_PORT
    try:
        with socket.create_connection((host, port), timeout=config.TIMEOUT):
            pass
    except OSError as exc:
        pytest.skip(
            f"gNMI/gRPC not reachable on {host}:{port} ({exc}) - "
            f"enable 'grpc' on the router to run these tests."
        )

    return {
        "target": (host, port),
        "username": config.USERNAME,
        "password": config.PASSWORD,
        "insecure": True,  # lab box: gRPC configured with 'no-tls'
    }
