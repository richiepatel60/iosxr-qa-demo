"""Configuration validation and closed-loop config automation over NETCONF.

Covers read-side compliance/drift checks plus the full write lifecycle:
create -> commit -> verify -> rollback, including a negative (error-path) test.
IOS-XR uses a *candidate* datastore, so config is staged then committed.
"""

import logging

import pytest
from ncclient.operations.rpc import RPCError

import config

log = logging.getLogger("iosxr-qa")

IFMGR_CFG = "http://cisco.com/ns/yang/Cisco-IOS-XR-ifmgr-cfg"

# Tokens that must appear in the running config (compliance / drift check).
# NOTE: NETCONF returns config as structured YANG/XML, NOT CLI text - so these
# are strings that genuinely appear in the XML (model names, element values),
# not CLI phrases like "ssh server".
REQUIRED_CONFIG = [
    "MgmtEth0/RP0/CPU0/0",  # management interface is present
    "netconf-yang",          # NETCONF-YANG agent is enabled
    "root-lr",               # a privileged user group is configured (AAA)
]


@pytest.fixture(autouse=True)
def _clean_candidate(netconf_session):
    """Isolate every config test by discarding any staged candidate changes
    before and after it runs, so one test can never leak config into another."""
    try:
        netconf_session.discard_changes()
    except Exception:  # noqa: BLE001 - best-effort hygiene
        pass
    yield
    try:
        netconf_session.discard_changes()
    except Exception:  # noqa: BLE001
        pass


def _loopback_config(name, description=None, delete=False):
    """Build an edit-config <config> body for a loopback interface."""
    if delete:
        return f"""
            <config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0">
              <interface-configurations xmlns="{IFMGR_CFG}">
                <interface-configuration xc:operation="delete">
                  <active>act</active>
                  <interface-name>{name}</interface-name>
                </interface-configuration>
              </interface-configurations>
            </config>
        """
    desc = f"<description>{description}</description>" if description else ""
    return f"""
        <config>
          <interface-configurations xmlns="{IFMGR_CFG}">
            <interface-configuration>
              <active>act</active>
              <interface-name>{name}</interface-name>
              {desc}
            </interface-configuration>
          </interface-configurations>
        </config>
    """


@pytest.mark.config
def test_running_config_contains_mgmt_interface(netconf_session):
    """Pull the <running> datastore and confirm the management interface exists."""
    reply = netconf_session.get_config(source="running")
    assert reply.data_xml, "Empty running configuration returned"
    assert config.MGMT_INTERFACE in reply.data_xml


@pytest.mark.config
@pytest.mark.parametrize("stanza", REQUIRED_CONFIG)
def test_required_config_present(netconf_session, stanza):
    """Compliance / drift check: each required stanza must be in running config."""
    running_xml = netconf_session.get_config(source="running").data_xml
    assert stanza in running_xml, f"Required config '{stanza}' missing (config drift!)"


@pytest.mark.config
def test_edit_config_loopback_round_trip(netconf_session):
    """Closed-loop automation: create a loopback, commit, verify, then delete."""
    loopback = "Loopback100"
    try:
        netconf_session.edit_config(
            target="candidate",
            config=_loopback_config(loopback, "QA-NETCONF-AUTOMATION"),
        )
        netconf_session.commit()
        log.info("Committed creation of %s", loopback)

        running_xml = netconf_session.get_config(source="running").data_xml
        assert loopback in running_xml, f"{loopback} not found after commit"
        log.info("Verified %s present in running config", loopback)
    finally:
        try:
            netconf_session.edit_config(
                target="candidate", config=_loopback_config(loopback, delete=True)
            )
            netconf_session.commit()
            log.info("Cleaned up %s", loopback)
        except Exception as exc:  # noqa: BLE001 - cleanup must not mask failures
            log.warning("Cleanup of %s failed: %s", loopback, exc)


@pytest.mark.config
def test_edit_running_datastore_is_rejected(netconf_session):
    """Negative test: IOS-XR has no writable-running datastore, so a direct
    write to <running> must be rejected. Confirms error paths are handled."""
    with pytest.raises(RPCError):
        netconf_session.edit_config(
            target="running", config=_loopback_config("Loopback199")
        )
    log.info("Device correctly rejected a direct write to the running datastore")


@pytest.mark.config
def test_discard_changes_rollback(netconf_session):
    """Rollback test: stage a change in candidate, then discard it and confirm
    the candidate is clean (never committed to running)."""
    loopback = "Loopback198"
    netconf_session.edit_config(
        target="candidate", config=_loopback_config(loopback, "SHOULD-BE-DISCARDED")
    )
    candidate_xml = netconf_session.get_config(source="candidate").data_xml
    assert loopback in candidate_xml, "Staged change not present in candidate"

    netconf_session.discard_changes()

    candidate_after = netconf_session.get_config(source="candidate").data_xml
    assert loopback not in candidate_after, "discard-changes did not clear candidate"
    log.info("Rollback via discard-changes verified for %s", loopback)
