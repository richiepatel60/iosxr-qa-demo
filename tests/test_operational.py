"""Live operational-state validation via NETCONF ``<get>`` + YANG oper models.

These are "grey-box" checks: an external client asserting on the device's
internal, live state (uptime, interface status) - not just CLI scraping.
"""

import logging

import pytest
import xmltodict

import config

log = logging.getLogger("iosxr-qa")

SHELLUTIL_OPER = "http://cisco.com/ns/yang/Cisco-IOS-XR-shellutil-oper"
PFI_IM_OPER = "http://cisco.com/ns/yang/Cisco-IOS-XR-pfi-im-cmd-oper"


def _interface_briefs(netconf_session):
    """Return the interface-brief list from the interface operational model."""
    filter_xml = f'<interfaces xmlns="{PFI_IM_OPER}"><interface-briefs/></interfaces>'
    reply = netconf_session.get(filter=("subtree", filter_xml))
    parsed = xmltodict.parse(reply.data_xml)
    briefs = parsed["data"]["interfaces"]["interface-briefs"]["interface-brief"]
    # xmltodict returns a dict for a single element, a list for many.
    return [briefs] if isinstance(briefs, dict) else briefs


@pytest.mark.operational
def test_system_uptime_and_hostname(netconf_session):
    """Retrieve live uptime + hostname via a subtree-filtered <get>."""
    filter_xml = f'<system-time xmlns="{SHELLUTIL_OPER}"/>'
    reply = netconf_session.get(filter=("subtree", filter_xml))
    uptime = xmltodict.parse(reply.data_xml)["data"]["system-time"]["uptime"]

    hostname = uptime["host-name"]
    seconds = int(uptime["uptime"])
    log.info("Router '%s' has been up for %d seconds", hostname, seconds)

    assert hostname, "No hostname returned in operational data"
    assert seconds > 0, "Router uptime should be greater than zero"


@pytest.mark.operational
def test_management_interface_is_operationally_up(netconf_session):
    """The management interface is operationally up."""
    briefs = _interface_briefs(netconf_session)
    mgmt = next(
        (b for b in briefs if b.get("interface-name") == config.MGMT_INTERFACE), None
    )
    assert mgmt is not None, f"{config.MGMT_INTERFACE} not present in operational data"

    state = mgmt.get("state", "")
    log.info("%s operational state = %s", config.MGMT_INTERFACE, state)
    assert "up" in state.lower(), f"{config.MGMT_INTERFACE} is not up (state={state})"


@pytest.mark.operational
def test_interface_inventory_reported(netconf_session):
    """The device reports an interface inventory with per-interface state."""
    briefs = _interface_briefs(netconf_session)
    assert len(briefs) >= 1, "No interfaces returned in operational data"

    up = [b.get("interface-name") for b in briefs if "up" in b.get("state", "").lower()]
    log.info("%d interfaces reported, %d operationally up", len(briefs), len(up))
    # Every interface entry should carry a state leaf we can reason about.
    assert all("state" in b for b in briefs), "An interface is missing its state"
