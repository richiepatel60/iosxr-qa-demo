"""Central connection settings for the IOS-XR test suite.

Every value is overridable via an environment variable, so no real credentials
or lab-specific addresses are ever committed. Lab-friendly defaults are provided
purely for convenience against a disposable CML sandbox.

    bash        : export XR_HOST=192.168.255.124 XR_PASSWORD='...'
    PowerShell  : $env:XR_HOST="192.168.255.124"; $env:XR_PASSWORD="..."
"""

import os

# Transport / auth ---------------------------------------------------------- #
HOST = os.getenv("XR_HOST", "192.168.255.40")
NETCONF_PORT = int(os.getenv("XR_PORT", "830"))
RESTCONF_PORT = int(os.getenv("XR_RESTCONF_PORT", "443"))
GNMI_PORT = int(os.getenv("XR_GNMI_PORT", "57400"))
USERNAME = os.getenv("XR_USERNAME", "cisco")
PASSWORD = os.getenv("XR_PASSWORD", "cisco")
TIMEOUT = int(os.getenv("XR_TIMEOUT", "30"))

# Well-known facts about an IOS-XRv9000 instance ---------------------------- #
MGMT_INTERFACE = "MgmtEth0/RP0/CPU0/0"
