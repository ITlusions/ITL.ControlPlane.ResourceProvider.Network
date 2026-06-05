# Pulumi Components for Network Provider — Implementation Plan

**Status**: Ready to implement  
**Effort**: 3-4 working days  
**Priority**: High (enables IaC deployment for all users)

---

## Overview

The Pulumi framework is **already built** in `ITL.ControlPlane.SDK v1.1.0+`. We need to create **Network Provider-specific components** that follow the established pattern.

### What Already Exists (in SDK)
- ✅ `ITLPulumiComponent` base class (dual-target, Azure + ITL)
- ✅ `ResourceGroup`, `ManagementGroup` components
- ✅ `AKSCluster`, `DefenderInitiative` components
- ✅ `PulumiStack`, `PulumiDeployment` orchestration
- ✅ Dynamic provider for ITL ControlPlane registration

### What We Need to Implement (Network Provider)
- ⏳ `VirtualNetwork` component
- ⏳ `Subnet` component
- ⏳ `NetworkSecurityGroup` component
- ⏳ `LoadBalancer` component
- ⏳ `VirtualNetworkPeering` component
- ⏳ `PrivateLink` component
- ⏳ `PrivateEndpoint` component
- ⏳ `VirtualNetworkPeeringService` component

---

## Component Implementation Pattern

All components follow this structure (see `ResourceGroup` in SDK as reference):

```python
"""
MyResource — ITL Pulumi component for <service>.

Provisions an Azure <service> with ITL platform defaults
and optionally registers it with the ITL ControlPlane API.
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


class MyResource(ITLPulumiComponent):
    """Azure MyResource with ITL platform defaults.

    Args:
        name: Logical component name
        location: Azure region
        [resource-specific args]
        azure_enabled: Provision Azure resources (default True)
        itl_enabled: Register with ITL ControlPlane (default True)
        subscription_id: ITL subscription
        opts: Pulumi resource options

    Outputs:
        resource_id: ARM resource ID
        resource_name: Resource name
    """

    resource_id: Output[str]
    resource_name: Output[str]

    def __init__(
        self,
        name: str,
        *,
        location: Input[str] = "westeurope",
        subscription_id: Optional[str] = None,
        azure_enabled: bool = True,
        itl_enabled: bool = True,
        itl_endpoint: Optional[str] = None,
        opts: Optional[pulumi.ResourceOptions] = None,
        **kwargs  # Resource-specific args
    ) -> None:
        super().__init__(
            "itl:network:MyResource",
            name,
            azure_enabled=azure_enabled,
            itl_enabled=itl_enabled,
            itl_endpoint=itl_endpoint,
            subscription_id=subscription_id,
            opts=opts,
        )

        resource_id = Output.from_input("")
        resource_name = Output.from_input(name)

        if azure_enabled:
            if not _AZURE_NATIVE_AVAILABLE:
                raise ImportError(
                    "pulumi-azure-native is required. "
                    "Install with: pip install pulumi-azure-native"
                )

            child_opts = pulumi.ResourceOptions(parent=self)
            
            # Create Azure resource here
            # Example:
            # resource = az_network.MyResource(
            #     name,
            #     resource_group_name=...,
            #     [properties],
            #     opts=child_opts,
            # )
            # resource_id = resource.id
            # resource_name = resource.name

        # ── ITL ControlPlane registration ─────────────────────────────────
        if itl_enabled:
            self._register_with_itl(
                "MyResource",
                {
                    "location": location,
                    # Other properties from kwargs
                },
                resource_name=name,
                subscription_id=subscription_id,
            )

        self.resource_id = resource_id
        self.resource_name = resource_name

        self.register_outputs({
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
        })
```

---

## Implementation Checklist

### Phase 1: Core Networking (Week 1)

#### 1. `VirtualNetwork` component
**File**: `src/itl_controlplane_sdk/pulumi/vnet.py`

```python
class VirtualNetwork(ITLPulumiComponent):
    """Azure Virtual Network with ITL defaults."""
    
    # Properties:
    # - name
    # - location
    # - address_space: List[str]  # e.g., ['10.0.0.0/16']
    # - dns_servers: Optional[List[str]]
    # - enable_ddos_protection: bool = False
    # - tags: Dict[str, str]
    
    # Azure side: pulumi_azure_native.network.VirtualNetwork
    # ITL side: Register as 'VirtualNetwork' resource type
    
    # Outputs:
    # - vnet_id: ARM resource ID
    # - vnet_name: Resource name
    # - address_space: List of address spaces
```

**Key Integration Points**:
- Azure: `pulumi_azure_native.network.VirtualNetwork`
- ITL: Register path: `/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks/{name}`
- Dual-target: When both enabled, deploy to Azure AND register in ITL simultaneously

#### 2. `Subnet` component
**File**: `src/itl_controlplane_sdk/pulumi/subnet.py`

```python
class Subnet(ITLPulumiComponent):
    """Azure Subnet with ITL defaults."""
    
    # Properties:
    # - virtual_network_id: str  # Parent VNet
    # - name: str
    # - address_prefix: str  # e.g., '10.0.1.0/24'
    # - service_endpoints: Optional[List[str]]
    # - delegation: Optional[Dict]  # For PaaS services
    # - nat_gateway_id: Optional[str]
    
    # Azure side: pulumi_azure_native.network.Subnet
    # ITL side: Register as 'Subnet' resource type
    
    # Outputs:
    # - subnet_id: ARM resource ID
    # - subnet_name: Resource name
    # - address_prefix: CIDR block
```

**Key Integration Points**:
- Azure: `pulumi_azure_native.network.Subnet`
- Parent relationship: Must reference parent VNet
- ITL: Register path: `{vnet_path}/subnets/{name}`

#### 3. `NetworkSecurityGroup` component
**File**: `src/itl_controlplane_sdk/pulumi/nsg.py`

```python
class NetworkSecurityGroup(ITLPulumiComponent):
    """Azure Network Security Group (firewall rules) with ITL defaults."""
    
    # Properties:
    # - location: str
    # - security_rules: List[Dict]  # Rules definition
    #   - name: str
    #   - priority: int (100-4096)
    #   - direction: 'Inbound' | 'Outbound'
    #   - access: 'Allow' | 'Deny'
    #   - protocol: 'Tcp' | 'Udp' | '*'
    #   - source_port_range: str
    #   - destination_port_range: str
    #   - source_address_prefix: str
    #   - destination_address_prefix: str
    # - tags: Dict[str, str]
    
    # Azure side: pulumi_azure_native.network.NetworkSecurityGroup
    # ITL side: Register as 'NetworkSecurityGroup' resource type
    
    # Outputs:
    # - nsg_id: ARM resource ID
    # - nsg_name: Resource name
    # - rules: Exported rule definitions
```

**Key Integration Points**:
- Azure: `pulumi_azure_native.network.NetworkSecurityGroup`
- Rules can be inline or separate `SecurityRule` resources
- ITL: Register path: `/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Network/networkSecurityGroups/{name}`

---

### Phase 2: Load Balancing (Week 1-2)

#### 4. `LoadBalancer` component
**File**: `src/itl_controlplane_sdk/pulumi/load_balancer.py`

```python
class LoadBalancer(ITLPulumiComponent):
    """Azure Load Balancer with ITL defaults."""
    
    # Properties:
    # - location: str
    # - sku: 'Standard' | 'Basic' (default 'Standard')
    # - public: bool (default True)  # Public vs Internal
    # - frontend_subnet_id: str  # For internal LB
    # - backend_pool_name: str
    # - health_check: Dict
    #   - protocol: 'Http' | 'Tcp'
    #   - path: str (for Http)
    #   - port: int
    #   - interval_seconds: int
    # - rules: List[Dict]  # Load balancing rules
    # - nat_rules: List[Dict]  # NAT inbound rules
    # - tags: Dict[str, str]
    
    # Azure side: pulumi_azure_native.network.LoadBalancer
    # + PublicIPAddress (if public=True)
    # + BackendAddressPool
    # + LoadBalancingRule
    # + HealthProbe
    
    # ITL side: Register as 'LoadBalancer' resource type
    
    # Outputs:
    # - lb_id: ARM resource ID
    # - lb_name: Resource name
    # - frontend_ip: Frontend public/private IP
    # - backend_pool_id: Backend pool ARM ID
```

**Key Integration Points**:
- Azure: `pulumi_azure_native.network.LoadBalancer` + related resources
- Dual NIC: Public frontend IP via `PublicIPAddress` resource
- ITL: Register path: `/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Network/loadBalancers/{name}`

#### 5. `PublicIP` component (helper)
**File**: `src/itl_controlplane_sdk/pulumi/public_ip.py`

```python
class PublicIP(ITLPulumiComponent):
    """Azure Public IP Address with ITL defaults."""
    
    # Properties:
    # - location: str
    # - sku: 'Standard' | 'Basic' (default 'Standard')
    # - allocation_method: 'Static' | 'Dynamic' (default 'Static')
    # - version: 'IPv4' | 'IPv6' (default 'IPv4')
    # - domain_name_label: Optional[str]
    # - tags: Dict[str, str]
    
    # Outputs:
    # - public_ip_id: ARM resource ID
    # - public_ip_address: The actual IP address
    # - fqdn: FQDN if domain label set
```

---

### Phase 3: Advanced Networking (Week 2-3)

#### 6. `VirtualNetworkPeering` component
**File**: `src/itl_controlplane_sdk/pulumi/vnet_peering.py`

```python
class VirtualNetworkPeering(ITLPulumiComponent):
    """Azure Virtual Network Peering with ITL defaults."""
    
    # Properties:
    # - local_vnet_id: str  # Source VNet
    # - remote_vnet_id: str  # Target VNet (can be cross-subscription)
    # - allow_forwarded_traffic: bool (default False)
    # - allow_gateway_transit: bool (default False)
    # - use_remote_gateways: bool (default False)
    # - allow_virtual_network_access: bool (default True)
    
    # Outputs:
    # - peering_id: ARM resource ID
    # - peering_name: Resource name
    # - peering_state: Current state ('Connected', 'Initiated', etc.)
```

**Key Integration Points**:
- Azure: `pulumi_azure_native.network.VirtualNetworkPeering`
- Must create both directions (local→remote AND remote→local)
- ITL: Register as 'VirtualNetworkPeering' resource type

#### 7. `PrivateLink` component
**File**: `src/itl_controlplane_sdk/pulumi/private_link.py`

```python
class PrivateLink(ITLPulumiComponent):
    """Azure Private Link Service with ITL defaults."""
    
    # Properties:
    # - location: str
    # - load_balancer_id: str  # Frontend config
    # - subnet_id: str  # Backend subnet
    # - nat_ip_config: List[Dict]  # NAT IP configs
    # - enable_proxy_protocol: bool (default False)
    # - visibility_scope: List[str]  # Subscriptions that can access
    
    # Outputs:
    # - private_link_id: ARM resource ID
    # - private_link_alias: Alias for consumers
    # - network_interfaces: Associated NICs
```

#### 8. `PrivateEndpoint` component
**File**: `src/itl_controlplane_sdk/pulumi/private_endpoint.py`

```python
class PrivateEndpoint(ITLPulumiComponent):
    """Azure Private Endpoint with ITL defaults."""
    
    # Properties:
    # - location: str
    # - subnet_id: str  # Where endpoint is placed
    # - private_connection_resource_id: str  # Target service
    # - group_ids: List[str]  # Subresources (e.g., ['blob'] for storage)
    # - private_dns_zone_id: Optional[str]
    
    # Outputs:
    # - endpoint_id: ARM resource ID
    # - endpoint_name: Resource name
    # - network_interfaces: NICs created
    # - private_ip_address: Private IP assigned
```

---

### Phase 4: Module & Examples (Week 3)

#### 9. Update `__init__.py`
**File**: `src/itl_controlplane_sdk/pulumi/__init__.py`

Add exports:
```python
from .vnet import VirtualNetwork
from .subnet import Subnet
from .nsg import NetworkSecurityGroup
from .load_balancer import LoadBalancer
from .public_ip import PublicIP
from .vnet_peering import VirtualNetworkPeering
from .private_link import PrivateLink
from .private_endpoint import PrivateEndpoint

__all__ = [
    # ... existing exports ...
    "VirtualNetwork",
    "Subnet",
    "NetworkSecurityGroup",
    "LoadBalancer",
    "PublicIP",
    "VirtualNetworkPeering",
    "PrivateLink",
    "PrivateEndpoint",
]
```

#### 10. Create Examples
**Files**: 
- `examples/pulumi_network_simple.py` — Basic VNet + Subnet + NSG
- `examples/pulumi_network_advanced.py` — Multi-tier with peering + LB
- `examples/pulumi_network_private_link.py` — Private Link + Endpoint

```python
# examples/pulumi_network_simple.py
import pulumi
from itl_controlplane_sdk.pulumi import (
    VirtualNetwork, Subnet, NetworkSecurityGroup, LoadBalancer
)

# Create VNet
vnet = VirtualNetwork(
    "prod-vnet",
    location="westeurope",
    address_space=["10.0.0.0/16"],
    subscription_id="sub-00000001",
)

# Create Subnets
frontend = Subnet(
    "frontend",
    virtual_network_id=vnet.vnet_id,
    address_prefix="10.0.1.0/24",
)

backend = Subnet(
    "backend",
    virtual_network_id=vnet.vnet_id,
    address_prefix="10.0.2.0/24",
)

# Create NSG
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
            "destination_port_range": "443",
            "source_address_prefix": "*",
            "destination_address_prefix": "*",
        }
    ],
)

# Create Load Balancer
lb = LoadBalancer(
    "api-lb",
    location="westeurope",
    public=True,
    backend_pool_name="api-pool",
)

# Exports
pulumi.export("vnet_id", vnet.vnet_id)
pulumi.export("frontend_subnet_id", frontend.subnet_id)
pulumi.export("lb_id", lb.lb_id)
pulumi.export("lb_ip", lb.frontend_ip)
```

---

## Testing Strategy

### Unit Tests
- **File**: `tests/unit/test_pulumi_components.py`
- Mock `pulumi_azure_native` and ITL API calls
- Test output generation for each component

### Integration Tests
- **File**: `tests/integration/test_pulumi_deploy.py`
- Deploy minimal stack in test environment (dry-run)
- Verify ARM JSON generation
- Verify ITL registration payload

### Example Validation
- Run each example with `pulumi preview` (no deploy)
- Verify output structure matches ARM schema

---

## Documentation Updates

### 1. Update main Pulumi README
- Add Network Provider section with examples
- Link to new components

### 2. Create `docs/pulumi-network.md`
- Architecture overview
- Component reference table
- Common patterns (multi-tier, peering, etc.)

### 3. Update Network Provider docs
- Add Pulumi as official deployment method
- Update tutorials/00-USER_EXAMPLES.md with working examples
- Update STATUS.md progress

---

## Dependencies

### New Requirements
```toml
# pyproject.toml additions
pulumi-azure-native = ">=2.0.0"  # Already in SDK
```

### Version Alignment
- Pulumi SDK: >=3.0.0 (already in SDK)
- Pulumi Automation: >=0.4.0 (already in SDK)
- pulumi-azure-native: >=2.0.0 (standard for Network resources)

---

## Implementation Order

**Recommended sequence** (builds hierarchy):

1. ✅ `PublicIP` (simplest, no dependencies)
2. ✅ `VirtualNetwork` (core, no dependencies)
3. ✅ `Subnet` (depends on VNet)
4. ✅ `NetworkSecurityGroup` (independent)
5. ✅ `LoadBalancer` (depends on PublicIP, Subnet)
6. ✅ `VirtualNetworkPeering` (depends on VNets)
7. ✅ `PrivateLink` (depends on LB, Subnet)
8. ✅ `PrivateEndpoint` (depends on Subnet)
9. ✅ Examples & tests
10. ✅ Documentation

---

## Success Criteria

- ✅ All 8 components implemented and tested
- ✅ Each component has `azure_enabled` and `itl_enabled` flags working
- ✅ Examples run successfully (`pulumi preview` passes)
- ✅ Components exportable from SDK `__init__.py`
- ✅ All tests passing (unit + integration)
- ✅ Documentation complete with CLI + portal examples
- ✅ End users can deploy complex topologies with simple Python code

---

## Effort Estimate

| Phase | Components | Time | Status |
|-------|-----------|------|--------|
| Phase 1 | VNet, Subnet, NSG | 1 day | Not started |
| Phase 2 | LB, PublicIP | 0.5 days | Not started |
| Phase 3 | Peering, PrivateLink, PrivateEndpoint | 1.5 days | Not started |
| Phase 4 | Examples, tests, docs | 1 day | Not started |
| **Total** | | **4 days** | |

---

## References

- [SDK Component Pattern](d:\repos\ITL.ControlPanel.SDK\src\itl_controlplane_sdk\pulumi\resource_group.py)
- [SDK Pulumi README](d:\repos\ITL.ControlPanel.SDK\src\itl_controlplane_sdk\pulumi\README.md)
- [Azure Native Pulumi Docs](https://www.pulumi.com/registry/packages/azure-native/)
- [Network Provider API Reference](d:\repos\ITL.ControlPlane.ResourceProvider.Network\docs\reference\API_REFERENCE.md)
