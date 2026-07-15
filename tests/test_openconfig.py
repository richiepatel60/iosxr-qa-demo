"""OpenConfig (vendor-neutral YANG) support tests.

The JD lists OpenConfig alongside NETCONF-YANG. These tests prove the device
both advertises OpenConfig models and returns real data through them.
"""

import logging

import pytest

import config

log = logging.getLogger("iosxr-qa")

OC_INTERFACES = "http://openconfig.net/yang/interfaces"


@pytest.mark.openconfig
def test_openconfig_models_advertised(netconf_session):
    """The device advertises OpenConfig models in its NETCONF capabilities."""
    oc_models = [c for c in netconf_session.server_capabilities if "openconfig" in c.lower()]
    log.info("Device advertised %d OpenConfig models", len(oc_models))
    assert oc_models, "Device advertised no OpenConfig models"


@pytest.mark.openconfig
def test_openconfig_interfaces_get(netconf_session):
    """Retrieve the interface list through the openconfig-interfaces model."""
    reply = netconf_session.get(filter=("subtree", f'<interfaces xmlns="{OC_INTERFACES}"/>'))
    assert reply.data_xml, "Empty response for openconfig-interfaces"
    assert config.MGMT_INTERFACE in reply.data_xml, (
        f"{config.MGMT_INTERFACE} not returned via openconfig-interfaces"
    )
    log.info("Retrieved %s via openconfig-interfaces", config.MGMT_INTERFACE)
