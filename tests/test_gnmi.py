"""gNMI tests (gRPC-based) - IOS-XR's native model-driven interface.

gNMI is what IOS-XR and the NCS optical platforms use for model-driven
management and streaming telemetry, so this is the most platform-authentic
protocol in the suite. The ``gnmi_target`` fixture skips these tests if gRPC is
not enabled on the device, so the suite stays green either way.

pygnmi is imported lazily inside each test so the suite still collects on a
machine that doesn't have it installed.
"""

import logging

import pytest

import config

log = logging.getLogger("iosxr-qa")


@pytest.mark.gnmi
def test_gnmi_capabilities(gnmi_target):
    """The gNMI Capabilities RPC returns a version and supported YANG models."""
    from pygnmi.client import gNMIclient

    with gNMIclient(**gnmi_target) as gc:
        caps = gc.capabilities()

    assert caps, "empty gNMI capabilities response"
    assert caps.get("gnmi_version"), "no gNMI version reported"

    models = caps.get("supported_models", [])
    log.info("gNMI version %s, %d supported models",
             caps.get("gnmi_version"), len(models))
    assert models, "device advertised no gNMI models"


@pytest.mark.gnmi
def test_gnmi_get_interfaces(gnmi_target):
    """A gNMI Get on openconfig-interfaces returns the management interface."""
    from pygnmi.client import gNMIclient

    with gNMIclient(**gnmi_target) as gc:
        response = gc.get(
            path=["openconfig-interfaces:interfaces"], encoding="json_ietf"
        )

    assert response, "empty gNMI Get response"
    assert config.MGMT_INTERFACE in str(response), (
        f"{config.MGMT_INTERFACE} not found in the gNMI Get response"
    )
    log.info("Retrieved %s via gNMI Get", config.MGMT_INTERFACE)
