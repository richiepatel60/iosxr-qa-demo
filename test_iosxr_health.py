"""
AI-Driven IOS-XR Manageability & Health Validation Suite
=========================================================

Automated test suite that validates the manageability surface and live
operational health of a Cisco IOS-XRv9000 router over **NETCONF** (RFC 6241)
using **YANG** data models.

Why this maps to the role
-------------------------
IOS-XR is the *common* network OS across Cisco's routing **and** optical
portfolios (e.g. NCS1010 / NCS1004 / NCS1014). The NETCONF-YANG manageability
workflow demonstrated here - session establishment, capability discovery,
running-config retrieval and operational-state validation - is identical whether
the target is a core router or an optical line system. This project shows that
manageability + Python test-automation skill set end to end.

Tooling
-------
- pytest     : test framework, fixtures and HTML reporting
- ncclient   : NETCONF client (transport over SSH, TCP/830)
- xmltodict  : turn NETCONF XML replies into Python dicts for clean assertions

Security note
-------------
Connection details are read from environment variables so that **no real
credentials are committed to source control**. Lab-friendly defaults are
provided purely for convenience against a disposable CML sandbox.

    PowerShell : $env:XR_HOST="192.168.255.40"; $env:XR_PASSWORD="<your-pw>"
    bash       : export XR_HOST=192.168.255.40 XR_PASSWORD=<your-pw>
"""

from __future__ import annotations

import logging
import os

import pytest
import xmltodict
from ncclient import manager
from ncclient.transport.errors import AuthenticationError, SSHError

# --------------------------------------------------------------------------- #
# Connection configuration (override any value via environment variables)      #
# --------------------------------------------------------------------------- #
HOST = os.getenv("XR_HOST", "192.168.255.40")
PORT = int(os.getenv("XR_PORT", "830"))
USERNAME = os.getenv("XR_USERNAME", "cisco")
PASSWORD = os.getenv("XR_PASSWORD", "cisco")
TIMEOUT = int(os.getenv("XR_TIMEOUT", "30"))

# Management interface we expect to find on an IOS-XRv9000 instance.
MGMT_INTERFACE = "MgmtEth0/RP0/CPU0/0"

log = logging.getLogger("iosxr-qa")


# --------------------------------------------------------------------------- #
# Fixture: a single NETCONF session shared by every test in this module        #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def netconf_session():
    """Open one NETCONF session and hand the live handle to the tests.

    ``scope="module"`` means the (relatively expensive) SSH + NETCONF handshake
    runs only once and every test reuses the same session. The ``yield`` splits
    setup from teardown - everything after it runs when the last test finishes,
    guaranteeing the session is always closed cleanly.
    """
    try:
        session = manager.connect(
            host=HOST,
            port=PORT,
            username=USERNAME,
            password=PASSWORD,
            hostkey_verify=False,   # lab box: do not verify the SSH host key
            look_for_keys=False,    # force password auth, ignore local SSH keys
            allow_agent=False,
            timeout=TIMEOUT,
            device_params={"name": "iosxr"},  # enable ncclient IOS-XR handling
        )
    except AuthenticationError:
        pytest.fail(
            f"NETCONF authentication failed for {USERNAME}@{HOST}:{PORT} - "
            f"check the XR_USERNAME / XR_PASSWORD environment variables."
        )
    except SSHError as exc:
        pytest.fail(
            f"Could not open a NETCONF/SSH transport to {HOST}:{PORT} - {exc}. "
            f"Is 'netconf-yang agent ssh' enabled and is the router reachable?"
        )

    # If manager.connect() had failed, the except blocks above would have ended
    # the test via pytest.fail(). This assert makes that guarantee explicit so the
    # static type-checker knows `session` is a live Manager (never None) below.
    assert session is not None
    log.info("NETCONF session %s established to %s", session.session_id, HOST)
    yield session

    # ---------------------------- teardown --------------------------------- #
    if session.connected:
        session.close_session()
        log.info("NETCONF session closed cleanly")


# --------------------------------------------------------------------------- #
# TEST 1 - Connectivity                                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.connectivity
def test_netconf_connection_established(netconf_session):
    """The NETCONF session is up and the server assigned a session-id."""
    assert netconf_session.connected is True, "NETCONF session reports not connected"
    assert netconf_session.session_id is not None, "No NETCONF session-id was returned"
    log.info("Connected to %s with session-id %s", HOST, netconf_session.session_id)


# --------------------------------------------------------------------------- #
# TEST 2 - Manageability surface (NETCONF/YANG capability discovery)           #
# --------------------------------------------------------------------------- #
@pytest.mark.manageability
def test_netconf_capabilities_advertised(netconf_session):
    """The device advertises NETCONF base support and a set of YANG models.

    Every YANG model the box supports is advertised as a capability URI, so a
    healthy model count is a good proxy for "this device is fully manageable
    via YANG" - exactly the manageability posture the role cares about.
    """
    caps = list(netconf_session.server_capabilities)
    assert caps, "Device advertised no NETCONF capabilities at all"

    base_caps = [c for c in caps if "netconf:base:1." in c]
    assert base_caps, "Device did not advertise a NETCONF base capability"

    yang_models = [c for c in caps if "module=" in c]
    log.info(
        "Device advertised %d capabilities including %d YANG models",
        len(caps),
        len(yang_models),
    )
    assert len(yang_models) >= 10, "Device advertised an unexpectedly small YANG surface"


# --------------------------------------------------------------------------- #
# TEST 3 - Running configuration validation                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.config
def test_running_config_contains_mgmt_interface(netconf_session):
    """Pull the <running> datastore and confirm the management interface exists."""
    reply = netconf_session.get_config(source="running")
    running_xml = reply.data_xml

    assert running_xml, "Empty running configuration returned"
    assert MGMT_INTERFACE in running_xml, (
        f"Management interface {MGMT_INTERFACE} was not found in the running config"
    )
    log.info("Found %s in the running configuration", MGMT_INTERFACE)


# --------------------------------------------------------------------------- #
# TEST 4 - Live operational state: uptime + hostname (<get> + xmltodict)        #
# --------------------------------------------------------------------------- #
@pytest.mark.operational
def test_get_system_uptime_and_hostname(netconf_session):
    """Retrieve live operational state using a NETCONF <get> with a subtree
    filter, then parse the XML reply into a dict with xmltodict."""
    system_time_filter = """
        <system-time xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-shellutil-oper"/>
    """
    reply = netconf_session.get(filter=("subtree", system_time_filter))
    parsed = xmltodict.parse(reply.data_xml)

    uptime = parsed["data"]["system-time"]["uptime"]
    hostname = uptime["host-name"]
    uptime_seconds = int(uptime["uptime"])

    log.info("Router '%s' has been up for %d seconds", hostname, uptime_seconds)
    assert hostname, "No hostname returned in operational data"
    assert uptime_seconds > 0, "Router uptime should be greater than zero"


# --------------------------------------------------------------------------- #
# TEST 5 - Grey-box health: management interface is operationally UP            #
# --------------------------------------------------------------------------- #
@pytest.mark.operational
def test_management_interface_is_operationally_up(netconf_session):
    """Confirm the management interface is operationally up via the interface
    operational YANG model - an on-the-box, grey-box state validation."""
    interface_filter = """
        <interfaces xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-pfi-im-cmd-oper">
            <interface-briefs/>
        </interfaces>
    """
    reply = netconf_session.get(filter=("subtree", interface_filter))
    parsed = xmltodict.parse(reply.data_xml)

    briefs = parsed["data"]["interfaces"]["interface-briefs"]["interface-brief"]
    if isinstance(briefs, dict):  # xmltodict returns a dict when there is one item
        briefs = [briefs]

    mgmt = next(
        (b for b in briefs if b.get("interface-name") == MGMT_INTERFACE), None
    )
    assert mgmt is not None, f"{MGMT_INTERFACE} not present in operational data"

    state = mgmt.get("state", "")
    log.info("%s operational state = %s", MGMT_INTERFACE, state)
    assert "up" in state.lower(), f"{MGMT_INTERFACE} is not up (state={state})"


# --------------------------------------------------------------------------- #
# TEST 6 - OpenConfig support (vendor-neutral YANG models named in the JD)      #
# --------------------------------------------------------------------------- #
@pytest.mark.openconfig
def test_openconfig_models_supported(netconf_session):
    """Confirm the device supports OpenConfig - the vendor-neutral YANG models
    the JD lists alongside NETCONF-YANG.

    Two levels of proof: (1) the device advertises OpenConfig modules in its
    capabilities, and (2) a live <get> against ``openconfig-interfaces`` returns
    real data including the management interface.
    """
    caps = list(netconf_session.server_capabilities)
    oc_models = [c for c in caps if "openconfig" in c.lower()]
    log.info("Device advertised %d OpenConfig models", len(oc_models))
    assert oc_models, "Device advertised no OpenConfig models"

    oc_interfaces_filter = """
        <interfaces xmlns="http://openconfig.net/yang/interfaces"/>
    """
    reply = netconf_session.get(filter=("subtree", oc_interfaces_filter))
    assert reply.data_xml, "Empty response for openconfig-interfaces"
    assert MGMT_INTERFACE in reply.data_xml, (
        f"{MGMT_INTERFACE} was not returned via openconfig-interfaces"
    )
    log.info("Retrieved %s via openconfig-interfaces", MGMT_INTERFACE)


# --------------------------------------------------------------------------- #
# TEST 7 - Config automation: create / verify / delete a loopback (edit-config) #
# --------------------------------------------------------------------------- #
@pytest.mark.config
def test_edit_config_loopback_round_trip(netconf_session):
    """Closed-loop configuration automation, not just read-only validation:

    1. <edit-config> creates a Loopback interface in the candidate datastore.
    2. <commit> promotes it to running.
    3. <get-config> confirms it landed in the running configuration.
    4. Teardown deletes it again so the device is left exactly as found.
    """
    loopback = "Loopback100"
    add_cfg = """
        <config>
          <interface-configurations xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-ifmgr-cfg">
            <interface-configuration>
              <active>act</active>
              <interface-name>Loopback100</interface-name>
              <description>QA-NETCONF-AUTOMATION</description>
            </interface-configuration>
          </interface-configurations>
        </config>
    """
    del_cfg = """
        <config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0">
          <interface-configurations xmlns="http://cisco.com/ns/yang/Cisco-IOS-XR-ifmgr-cfg">
            <interface-configuration xc:operation="delete">
              <active>act</active>
              <interface-name>Loopback100</interface-name>
            </interface-configuration>
          </interface-configurations>
        </config>
    """
    try:
        netconf_session.edit_config(target="candidate", config=add_cfg)
        netconf_session.commit()
        log.info("Committed creation of %s", loopback)

        reply = netconf_session.get_config(source="running")
        assert loopback in reply.data_xml, (
            f"{loopback} was not found in the running config after commit"
        )
        log.info("Verified %s is present in the running configuration", loopback)
    finally:
        # Always attempt to remove the test interface so the box is left clean.
        try:
            netconf_session.edit_config(target="candidate", config=del_cfg)
            netconf_session.commit()
            log.info("Cleaned up %s", loopback)
        except Exception as exc:  # noqa: BLE001 - cleanup must never mask a failure
            log.warning("Cleanup of %s failed: %s", loopback, exc)
