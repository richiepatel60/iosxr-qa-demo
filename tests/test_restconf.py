"""RESTCONF basics - the same manageability data over HTTPS/JSON (RFC 8040).

RESTCONF is the REST-flavoured sibling of NETCONF named in the JD. These tests
exercise the ``restconf`` fixture, which skips them automatically if the agent
is not enabled on the device - so the suite stays green on NETCONF-only images.
"""

import logging

import pytest

import config

log = logging.getLogger("iosxr-qa")


@pytest.mark.restconf
def test_restconf_yang_library(restconf):
    """GET the YANG library over RESTCONF and confirm a well-formed JSON reply."""
    session, base_url = restconf
    resp = session.get(
        f"{base_url}/data/ietf-yang-library:modules-state", timeout=config.TIMEOUT
    )
    assert resp.status_code == 200, f"Unexpected HTTP {resp.status_code}"
    assert "ietf-yang-library:modules-state" in resp.json(), "Malformed RESTCONF payload"
    log.info("RESTCONF yang-library returned HTTP 200")


@pytest.mark.restconf
def test_restconf_get_interfaces(restconf):
    """GET the interface list over RESTCONF (openconfig-interfaces)."""
    session, base_url = restconf
    resp = session.get(
        f"{base_url}/data/openconfig-interfaces:interfaces", timeout=config.TIMEOUT
    )
    assert resp.status_code in (200, 204), f"Unexpected HTTP {resp.status_code}"
    if resp.status_code == 200:
        assert config.MGMT_INTERFACE in resp.text, "Mgmt interface missing from RESTCONF reply"
    log.info("RESTCONF interfaces GET returned HTTP %d", resp.status_code)
