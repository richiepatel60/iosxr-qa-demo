"""Transport + manageability-surface tests.

Proves the device is reachable over NETCONF and advertises a healthy set of
YANG models - the foundation everything else builds on.
"""

import logging

import pytest

import config

log = logging.getLogger("iosxr-qa")


@pytest.mark.connectivity
def test_netconf_connection_established(netconf_session):
    """The NETCONF session is up and the server assigned a session-id."""
    assert netconf_session.connected is True, "NETCONF session reports not connected"
    assert netconf_session.session_id is not None, "No NETCONF session-id returned"
    log.info("Connected to %s with session-id %s", config.HOST, netconf_session.session_id)


@pytest.mark.manageability
def test_netconf_capabilities_advertised(netconf_session):
    """The device advertises NETCONF base support plus many YANG models.

    Each supported model is advertised as a capability URI during the <hello>
    exchange, so a healthy count is a good proxy for "fully manageable via YANG".
    """
    caps = list(netconf_session.server_capabilities)
    assert caps, "Device advertised no NETCONF capabilities"

    assert any("netconf:base:1." in c for c in caps), "No NETCONF base capability"

    yang_models = [c for c in caps if "module=" in c]
    log.info("Advertised %d capabilities including %d YANG models",
             len(caps), len(yang_models))
    assert len(yang_models) >= 10, "Unexpectedly small YANG surface"
