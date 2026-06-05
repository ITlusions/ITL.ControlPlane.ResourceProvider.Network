# Pulumi Components for Network Resource Provider
## Implementation Plan for Network Provider Team

**Ownership**: ITL.ControlPlane.ResourceProvider.Network team  
**Status**: Ready to implement  
**Effort**: 3-4 working days  
**Priority**: High (enables IaC deployment for all users)

---

## Overview

The Network Resource Provider team will implement **Pulumi components** that allow users to deploy networking infrastructure as code.

### Architecture Decision

- ✅ **Location**: `ITL.ControlPlane.ResourceProvider.Network/src/itl_controlplane_network_pulumi/`
- ✅ **Package Name**: `itl-controlplane-network-pulumi` (published to PyPI)
- ✅ **Dependency**: Extends `itl-controlplane-sdk` (for base `ITLPulumiComponent`)
- ✅ **Publishing**: Auto-publish on release via GitHub Actions (like SDK does)
- ✅ **Installation**: `pip install itl-controlplane-network-pulumi`

### Why This Approach?

| Aspect | Benefit |
|--------|---------|
| **Owned by Network Team** | Team knows resource API inside/out → better components |
| **Separate Package** | Can ship faster than SDK (no SDK release cycle dependency) |
| **Extends SDK Base** | Reuses `ITLPulumiComponent` framework (no duplication) |
| **Auto-publishes** | Same GitHub Actions workflow as SDK |
| **Users get latest** | Can pin to Network Provider package independently |

---

## Repository Structure

```
ITL.ControlPlane.ResourceProvider.Network/
├── src/
│   └── itl_controlplane_network_pulumi/     ← NEW
│       ├── __init__.py
│       ├── vnet.py                          # VirtualNetwork component
│       ├── subnet.py                        # Subnet component
│       ├── nsg.py                           # NetworkSecurityGroup component
│       ├── load_balancer.py                 # LoadBalancer component
│       ├── public_ip.py                     # PublicIP component
│       ├── vnet_peering.py                  # VirtualNetworkPeering component
│       ├── private_link.py                  # PrivateLink component
│       ├── private_endpoint.py              # PrivateEndpoint component
│       └── _utils.py                        # Shared helpers
├── tests/
│   └── pulumi/                              # Pulumi-specific tests
│       ├── test_vnet.py
│       ├── test_subnet.py
│       └── ...
├── examples/
│   └── pulumi/                              ← NEW
│       ├── simple_vnet.py                   # Basic example
│       ├── multi_tier_app.py                # Advanced example
│       └── private_link.py                  # Private Link example
├── docs/
│   ├── pulumi/                              ← NEW
│   │   ├── README.md                        # Overview & getting started
│   │   ├── COMPONENTS.md                    # Component reference
│   │   ├── ARCHITECTURE.md                  # Design decisions
│   │   └── EXAMPLES.md                      # Full examples
│   └── ... (existing docs)
├── pyproject.toml                           ← UPDATE
└── .github/workflows/
    └── publish.yml                          ← UPDATE
```

---

## Implementation Phases

### Phase 1: Project Setup (Day 0.5)

#### 1.1 Create Package Structure
```bash
mkdir -p src/itl_controlplane_network_pulumi
touch src/itl_controlplane_network_pulumi/__init__.py
```

#### 1.2 Update `pyproject.toml`

```toml
[project]
name = "itl-controlplane-network-pulumi"
version = "0.1.0"  # Separate from provider version
description = "Pulumi components for ITL Network Resource Provider"

[project.optional-dependencies]
pulumi = [
    "pulumi>=3.0.0",
    "pulumi-automation>=0.4.0",
    "pulumi-azure-native>=2.0.0",
    "itl-controlplane-sdk>=1.1.0",  # Base components
]
dev = [
    # existing dev deps...
    "pytest-pulumi>=0.1.0",  # Pulumi testing
]
```

#### 1.3 Update `.github/workflows/publish.yml`

Add step to detect and publish Pulumi package separately:

```yaml
- name: Publish Pulumi Package to PyPI
  if: startsWith(github.ref, 'refs/tags/v')
  run: |
    # Build Pulumi package
    cd src/itl_controlplane_network_pulumi
    pip install build
    python -m build
    # Publish (same OIDC credentials as main package)
    pip install twine
    python -m twine upload dist/*
  env:
    TWINE_REPOSITORY_URL: https://upload.pypi.org/legacy/
```

---

### Phase 2: Core Components (Days 1-2)

All components follow the **SDK pattern** established in `ResourceGroup`:

#### 2.1 Create `_utils.py` (Shared Helpers)

```python
"""Shared utilities for Network Resource Provider Pulumi components."""

from typing import Dict, Any, Optional
import pulumi
from itl_controlplane_sdk.pulumi import ITLPulumiComponent


def validate_cidr_block(cidr: str) -> bool:
    """Validate CIDR notation."""
    import ipaddress
    try:
        ipaddress.ip_network(cidr, strict=False)
        return True
    except ValueError:
        return False


def default_resource_group_name(component_name: str) -> str:
    """Generate default resource group name from component name."""
    return f"{component_name}-rg"
```

#### 2.2 Create `public_ip.py`

```python
"""
PublicIP — ITL Pulumi component for Azure Public IP Address.
"""

from typing import Dict, Optional
import pulumi
from pulumi import Input, Output
from itl_controlplane_sdk.pulumi import ITLPulumiComponent

try:
    import pulumi_azure_native.network as az_network
    _AZURE_NATIVE_AVAILABLE = True
except ImportError:
    _AZURE_NATIVE_AVAILABLE = False


class PublicIP(ITLPulumiComponent):
    """Azure Public IP Address with ITL platform defaults.

    Args:
        name: Logical component name
        location: Azure region (default "westeurope")
        sku: 'Standard' or 'Basic' (default 'Standard')
        allocation_method: 'Static' or 'Dynamic' (default 'Static')
        version: 'IPv4' or 'IPv6' (default 'IPv4')
        domain_name_label: Optional DNS label
        resource_group_name: Override RG name
        subscription_id: ITL subscription
        azure_enabled: Deploy to Azure (default True)
        itl_enabled: Register with ITL (default True)
        opts: Pulumi resource options

    Outputs:
        public_ip_id: ARM resource ID
        public_ip_address: The actual IP
        fqdn: FQDN if domain label set
    """

    public_ip_id: Output[str]
    public_ip_address: Output[str]
    fqdn: Output[Optional[str]]

    def __init__(
        self,
        name: str,
        *,
        location: Input[str] = "westeurope",
        sku: str = "Standard",
        allocation_method: str = "Static",
        version: str = "IPv4",
        domain_name_label: Optional[str] = None,
        resource_group_name: Optional[str] = None,
        subscription_id: Optional[str] = None,
        azure_enabled: bool = True,
        itl_enabled: bool = True,
        itl_endpoint: Optional[str] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
    ) -> None:
        super().__init__(
            "itl:network:PublicIP",
            name,
            azure_enabled=azure_enabled,
            itl_enabled=itl_enabled,
            itl_endpoint=itl_endpoint,
            subscription_id=subscription_id,
            opts=opts,
        )

        public_ip_id = Output.from_input("")
        public_ip_address = Output.from_input("")
        fqdn = Output.from_input(None)

        if azure_enabled:
            if not _AZURE_NATIVE_AVAILABLE:
                raise ImportError(
                    "pulumi-azure-native required. "
                    "Install: pip install itl-controlplane-network-pulumi[pulumi]"
                )

            child_opts = pulumi.ResourceOptions(parent=self)

            pip = az_network.PublicIPAddress(
                name,
                resource_group_name=resource_group_name or self._resource_group,
                public_ip_address_name=name,
                location=location,
                sku=az_network.PublicIPAddressSkuArgs(name=sku),
                public_ip_allocation_method=allocation_method,
                public_ip_address_version=version,
                domain_name_label=domain_name_label,
                opts=child_opts,
            )

            public_ip_id = pip.id
            public_ip_address = pip.ip_address
            fqdn = pip.fqdn

        # ITL registration
        if itl_enabled:
            self._register_with_itl(
                "PublicIPAddress",
                {
                    "location": location,
                    "sku": {"name": sku},
                    "publicIPAllocationMethod": allocation_method,
                    "publicIPAddressVersion": version,
                },
                resource_name=name,
            )

        self.public_ip_id = public_ip_id
        self.public_ip_address = public_ip_address
        self.fqdn = fqdn

        self.register_outputs({
            "public_ip_id": self.public_ip_id,
            "public_ip_address": self.public_ip_address,
            "fqdn": self.fqdn,
        })
```

#### 2.3 Create `vnet.py`

Follow the same pattern as PublicIP. Use `ResourceGroup` from SDK as template.

#### 2.4 Create `subnet.py`, `nsg.py`, etc.

Same approach — each file ~150-200 lines, following SDK pattern.

---

### Phase 3: Integration & Export (Day 2.5)

#### 3.1 Create `__init__.py`

```python
"""
Pulumi components for ITL ControlPlane Network Resource Provider.

Components
----------
- VirtualNetwork — Azure VNet with ITL defaults
- Subnet — Subnet with ITL defaults
- NetworkSecurityGroup — NSG with ITL defaults
- LoadBalancer — Load Balancer with ITL defaults
- PublicIP — Public IP address
- VirtualNetworkPeering — VNet-to-VNet peering
- PrivateLink — Private Link service
- PrivateEndpoint — Private endpoint

Usage
-----
Install:
    pip install itl-controlplane-network-pulumi

Deploy:
    import pulumi
    from itl_controlplane_network_pulumi import VirtualNetwork, Subnet

    vnet = VirtualNetwork("prod-vnet", address_space=["10.0.0.0/16"])
    subnet = Subnet("frontend", virtual_network_id=vnet.vnet_id)

    pulumi.export("vnet_id", vnet.vnet_id)
"""

__version__ = "0.1.0"
__author__ = "ITL Network Provider Team"

from .public_ip import PublicIP
from .vnet import VirtualNetwork
from .subnet import Subnet
from .nsg import NetworkSecurityGroup
from .load_balancer import LoadBalancer
from .vnet_peering import VirtualNetworkPeering
from .private_link import PrivateLink
from .private_endpoint import PrivateEndpoint

__all__ = [
    "PublicIP",
    "VirtualNetwork",
    "Subnet",
    "NetworkSecurityGroup",
    "LoadBalancer",
    "VirtualNetworkPeering",
    "PrivateLink",
    "PrivateEndpoint",
]
```

---

### Phase 4: Examples & Tests (Days 3-3.5)

#### 4.1 Create `examples/pulumi/simple_vnet.py`

```python
#!/usr/bin/env python3
"""
Simple example: Deploy a VNet with 2 subnets and NSG.

Run:
    cd examples/pulumi
    pulumi new python
    pulumi config set subscription_id 'sub-00000001'
    pulumi up
"""

import pulumi
from itl_controlplane_network_pulumi import (
    VirtualNetwork,
    Subnet,
    NetworkSecurityGroup,
)

# Create VNet
vnet = VirtualNetwork(
    "prod-vnet",
    address_space=["10.0.0.0/16"],
    location="westeurope",
)

# Create frontend subnet
frontend = Subnet(
    "frontend",
    virtual_network_id=vnet.vnet_id,
    address_prefix="10.0.1.0/24",
)

# Create backend subnet
backend = Subnet(
    "backend",
    virtual_network_id=vnet.vnet_id,
    address_prefix="10.0.2.0/24",
)

# Create NSG for frontend
nsg_frontend = NetworkSecurityGroup(
    "nsg-frontend",
    location="westeurope",
    security_rules=[
        {
            "name": "allow-https",
            "priority": 100,
            "direction": "Inbound",
            "access": "Allow",
            "protocol": "TCP",
            "source_port_range": "*",
            "destination_port_range": "443",
            "source_address_prefix": "*",
            "destination_address_prefix": "*",
        }
    ],
)

# Exports
pulumi.export("vnet_id", vnet.vnet_id)
pulumi.export("frontend_subnet_id", frontend.subnet_id)
pulumi.export("backend_subnet_id", backend.subnet_id)
pulumi.export("nsg_id", nsg_frontend.nsg_id)
```

#### 4.2 Create Tests

```python
# tests/pulumi/test_vnet.py
import pytest
import pulumi
from itl_controlplane_network_pulumi import VirtualNetwork


def test_vnet_creation():
    """Test VirtualNetwork component creation."""
    vnet = VirtualNetwork(
        "test-vnet",
        address_space=["10.0.0.0/16"],
        azure_enabled=False,  # Skip Azure in unit tests
        itl_enabled=False,
    )
    assert vnet is not None


@pytest.mark.asyncio
async def test_vnet_dual_target():
    """Test dual-target deployment (Azure + ITL)."""
    # This would require mocking Azure and ITL APIs
    pass
```

---

### Phase 5: Documentation (Day 3.5-4)

#### 5.1 Create `docs/pulumi/README.md`

```markdown
# Pulumi Components for Network Provider

Deploy networking infrastructure as code using Python + Pulumi.

## Installation

```bash
pip install itl-controlplane-network-pulumi[pulumi]
```

## Quick Start

```python
import pulumi
from itl_controlplane_network_pulumi import VirtualNetwork, Subnet

vnet = VirtualNetwork("prod-vnet", address_space=["10.0.0.0/16"])
subnet = Subnet("frontend", virtual_network_id=vnet.vnet_id)

pulumi.export("vnet_id", vnet.vnet_id)
```

Deploy:
```bash
pulumi up
```

## Components

- **VirtualNetwork** — Azure VNet
- **Subnet** — Subnets within VNets
- **NetworkSecurityGroup** — Firewall rules
- **LoadBalancer** — Load Balancer
- **PublicIP** — Public IP addresses
- **VirtualNetworkPeering** — VNet-to-VNet peering
- **PrivateLink** — Private Link services
- **PrivateEndpoint** — Private endpoints

See [COMPONENTS.md](COMPONENTS.md) for detailed reference.
```

#### 5.2 Update Network Provider main `docs/`

Add section to `docs/README.md` or `docs/tutorials/00-USER_EXAMPLES.md`:

```markdown
## Option 5: Pulumi (Python) — Official Network Provider Components ✅

**Status**: Available now via `itl-controlplane-network-pulumi` package

Install:
```bash
pip install itl-controlplane-network-pulumi[pulumi]
```

See: [docs/pulumi/](pulumi/README.md)
```

---

## Publishing Workflow

### For Each Release

1. **Version bump** in Network Provider `pyproject.toml`:
   ```toml
   [project]
   version = "1.2.0"  # Main provider version
   
   [project.optional-dependencies]
   pulumi = [
       ...
   ]
   ```

2. **Pulumi package version** also bumps in `src/itl_controlplane_network_pulumi/__init__.py`:
   ```python
   __version__ = "1.2.0"  # Same as provider
   ```

3. **GitHub Actions** automatically:
   - Builds `itl-controlplane-network-pulumi` wheel
   - Publishes to PyPI
   - Tags with `vX.Y.Z`

4. **Users install**:
   ```bash
   pip install itl-controlplane-network-pulumi==1.2.0
   ```

---

## Dependencies

### Direct
- `itl-controlplane-sdk>=1.1.0` (base `ITLPulumiComponent`)
- `pulumi>=3.0.0` (optional, only if using Pulumi features)
- `pulumi-azure-native>=2.0.0` (optional)

### Inherited from SDK
- `pulumi-automation>=0.4.0`
- Python 3.9+

---

## Team Responsibilities

### Network Provider Team
- ✅ Implement 8 Pulumi components
- ✅ Write unit + integration tests
- ✅ Create examples
- ✅ Maintain components
- ✅ Document API changes
- ✅ Publish package on release

### SDK Team
- ✅ Maintain `ITLPulumiComponent` base class
- ✅ Handle dual-target deployment framework
- ✅ Support new Network Provider components (as consumers, not maintainers)

---

## Testing Strategy

### Unit Tests (Fast, local)
- Mock `pulumi_azure_native`
- Mock ITL API calls
- Verify Pulumi resource trees
- Location: `tests/pulumi/test_*.py`

### Integration Tests (Slower, realistic)
- Deploy to test environment
- Verify ARM JSON generation
- Verify ITL registration payloads
- Location: `tests/pulumi/integration/`

### Example Validation
- `pulumi preview` on each example (no deploy)
- Verify output structure matches ARM schema

---

## Timeline & Effort

| Phase | Tasks | Time | Owner |
|-------|-------|------|-------|
| Setup | pyproject.toml, publish.yml, package structure | 4h | Network Team |
| Components | Implement 8 components | 16h | Network Team |
| Integration | Export, tests, CI/CD validation | 8h | Network Team |
| Examples | Create 3+ working examples | 4h | Network Team |
| Docs | Component reference, tutorials | 4h | Network Team |
| **Total** | | **36h (4.5 days)** | Network Team |

---

## Success Criteria

✅ All 8 components implemented  
✅ Components exportable from `itl_controlplane_network_pulumi`  
✅ Package publishes to PyPI automatically  
✅ All examples run successfully (`pulumi preview` passes)  
✅ Tests pass (unit + integration)  
✅ Documentation complete  
✅ End users can deploy complex topologies with Python code  

---

## References

- [Existing SDK Pattern](d:\repos\ITL.ControlPanel.SDK\src\itl_controlplane_sdk\pulumi\resource_group.py)
- [SDK Pulumi Base](d:\repos\ITL.ControlPanel.SDK\src\itl_controlplane_sdk\pulumi\component.py)
- [Network Provider API](docs/reference/API_REFERENCE.md)
- [Pulumi Automation API](https://www.pulumi.com/docs/automation/)
- [Azure Native Provider](https://www.pulumi.com/registry/packages/azure-native/)
