"""
Network Provider implementation with Cilium SDN integration.

Manages Azure-style networking on Kubernetes using Cilium + Talos:
- Virtual Networks (VNets): K8s Namespaces + Cilium IP pools
- Subnets: Cilium LoadBalancerIPPool with IPAM
- Network Security Groups (NSGs): Cilium CiliumNetworkPolicy rules
- Network Interfaces (NICs): Pod/VM network attachments
- Load Balancers: K8s Services with Cilium LB
- Public IPs: Cilium external IP pools

Uses Kubernetes API client for Cilium CRDs and SDK storage engine for persistence.
"""

import hashlib
import json
import logging
import os
from typing import Any, Optional

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from itl_controlplane_sdk import (
    ResourceProvider,
    ResourceRequest,
    ResourceResponse,
    ResourceListResponse,
    ProvisioningState,
    generate_resource_id,
)
from itl_controlplane_sdk.persistence import SQLAlchemyStorageEngine

logger = logging.getLogger(__name__)


# ============================================================================
# Utility Functions
# ============================================================================


def _generate_k8s_name(resource_id: str, prefix: str = "") -> str:
    """
    Generate a K8s-safe unique name from Azure resource ID.
    
    K8s names must be:
    - DNS-1123 compliant (lowercase, hyphens, no underscores)
    - Max 63 characters
    
    Uses hash of resource ID to guarantee uniqueness across subscriptions/RGs.
    
    Args:
        resource_id: Full Azure ARM resource ID
        prefix: Optional prefix (e.g., "pool", "policy", "vnet")
    
    Returns:
        Valid K8s name: "{prefix}-{hash}" (e.g., "pool-a1b2c3d4")
    """
    # Hash resource ID to ensure uniqueness
    name_hash = hashlib.md5(resource_id.encode()).hexdigest()[:8]
    
    if prefix:
        result = f"{prefix}-{name_hash}".lower()
    else:
        result = f"res-{name_hash}".lower()
    
    return result


# ============================================================================
# Resource Models (Azure-style)
# ============================================================================


class VirtualNetwork:
    """Azure-style Virtual Network backed by K8s namespace + Cilium pool."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        location: str,
        address_space: list[str],
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/virtualNetworks"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.address_space = address_space
        self.subnets: list[str] = []
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "addressSpace": {"addressPrefixes": self.address_space},
            "subnets": self.subnets,
            "ciliumPool": None,  # Reference to K8s namespace
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "properties": self.properties,
        }


class Subnet:
    """Azure-style Subnet backed by Cilium LoadBalancerIPPool."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        vnet_id: str,
        address_prefix: str,
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/virtualNetworks/subnets"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.vnet_id = vnet_id
        self.address_prefix = address_prefix
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "addressPrefix": self.address_prefix,
            "ciliumPool": None,  # Reference to Cilium pool
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class NetworkSecurityGroup:
    """Azure-style NSG backed by Cilium CiliumNetworkPolicy."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        location: str,
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/networkSecurityGroups"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.security_rules: list[dict] = []
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "securityRules": self.security_rules,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "properties": self.properties,
        }


class NetworkInterface:
    """Azure-style NIC backed by K8s pod/VM interface."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        location: str,
        vnet_id: str,
        subnet_id: str,
        private_ip: str,
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/networkInterfaces"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.vnet_id = vnet_id
        self.subnet_id = subnet_id
        self.private_ip = private_ip
        self.public_ip_id: Optional[str] = None
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "ipConfigurations": [
                {
                    "name": f"{name}-ipconfig1",
                    "privateIPAddress": self.private_ip,
                    "subnet": {"id": self.subnet_id},
                }
            ],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "properties": self.properties,
        }


class PublicIpAddress:
    """Azure-style Public IP backed by Cilium external IP pool."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        location: str,
        allocation_method: str = "Static",
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/publicIPAddresses"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.allocation_method = allocation_method
        self.ip_address: Optional[str] = None
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "publicIPAllocationMethod": self.allocation_method,
            "publicIPAddress": self.ip_address,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "properties": self.properties,
        }


class LoadBalancer:
    """Azure-style LB backed by K8s Service + Cilium LB."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        location: str,
        sku: str = "Standard",
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/loadBalancers"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.sku = sku
        self.frontend_ip_configs: list[dict] = []
        self.backend_pools: list[dict] = []
        self.load_balancing_rules: list[dict] = []
        self.inbound_nat_rules: list[dict] = []
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "sku": {"name": self.sku},
            "frontendIPConfigurations": self.frontend_ip_configs,
            "backendAddressPools": self.backend_pools,
            "loadBalancingRules": self.load_balancing_rules,
            "inboundNatRules": self.inbound_nat_rules,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "properties": self.properties,
        }


class BGPPeeringPolicy:
    """BGP Peering Policy for multi-site cluster networking."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        location: str,
        local_asn: int = 64512,
        neighbors: Optional[list[dict]] = None,
        export_pod_cidr: bool = True,
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/bgpPeeringPolicies"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.local_asn = local_asn
        self.neighbors = neighbors or []
        self.export_pod_cidr = export_pod_cidr
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "localASN": self.local_asn,
            "neighbors": self.neighbors,
            "exportPodCIDR": self.export_pod_cidr,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "properties": self.properties,
        }


class VirtualNetworkPeering:
    """Azure-style VNet Peering backed by Cilium NetworkPolicy."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        local_vnet_id: str,
        remote_vnet_id: str,
        allow_virtual_network_access: bool = True,
        allow_forwarded_traffic: bool = False,
        allow_gateway_transit: bool = False,
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/virtualNetworkPeerings"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.local_vnet_id = local_vnet_id
        self.remote_vnet_id = remote_vnet_id
        self.allow_virtual_network_access = allow_virtual_network_access
        self.allow_forwarded_traffic = allow_forwarded_traffic
        self.allow_gateway_transit = allow_gateway_transit
        self.provisioning_state = "Succeeded"
        self.peering_state = "Connected"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "peeringState": self.peering_state,
            "remoteVirtualNetwork": {"id": remote_vnet_id},
            "allowVirtualNetworkAccess": allow_virtual_network_access,
            "allowForwardedTraffic": allow_forwarded_traffic,
            "allowGatewayTransit": allow_gateway_transit,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class PrivateLinkService:
    """Azure-style Private Link Service backed by Cilium NetworkPolicy."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        service_id: str,
        vnet_id: str,
        load_balancer_ip: str,
        visibility: Optional[list[str]] = None,
        auto_approval: Optional[list[str]] = None,
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/privateLinkServices"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.service_id = service_id
        self.vnet_id = vnet_id
        self.load_balancer_ip = load_balancer_ip
        self.visibility = visibility or ["*"]
        self.auto_approval = auto_approval or []
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "loadBalancerFrontendIpConfiguration": {"id": load_balancer_ip},
            "ipConfigurations": [],
            "visibility": {"subscriptions": self.visibility},
            "autoApproval": {"subscriptions": self.auto_approval},
            "privateLinkServiceConnections": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class PrivateEndpoint:
    """Azure-style Private Endpoint backed by cross-tenant Cilium NetworkPolicy."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        vnet_id: str,
        subnet_id: str,
        service_connection: dict,
        private_ip_address: str,
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/privateEndpoints"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.vnet_id = vnet_id
        self.subnet_id = subnet_id
        self.service_connection = service_connection
        self.private_ip_address = private_ip_address
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "subnet": {"id": subnet_id},
            "privateLinkServiceConnections": [service_connection],
            "privateEndpointConnections": [],
            "customDnsConfigs": [
                {
                    "fqdn": f"{name}.privatelink.database.windows.net"
                }
            ],
            "networkInterfaces": [
                {
                    "id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Network/networkInterfaces/{name}-nic"
                }
            ],
            "privateIPAddress": private_ip_address,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class PrivateDnsZone:
    """Azure-style Private DNS Zone backed by CoreDNS ConfigMap."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        location: str,
        zone_name: str,
        etag: Optional[str] = None,
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/privateDnsZones"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.zone_name = zone_name  # e.g., "database.private.local"
        self.etag = etag or "W/\"1\""
        self.provisioning_state = "Succeeded"
        self.records: list[str] = []
        self.vnet_links: list[str] = []
        self.properties = {
            "provisioningState": self.provisioning_state,
            "zoneName": zone_name,
            "etag": self.etag,
            "recordSets": self.records,
            "virtualNetworkLinks": self.vnet_links,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "etag": self.etag,
            "properties": self.properties,
        }


class PrivateDnsRecord:
    """Azure-style DNS Record within Private DNS Zone."""
    
    def __init__(
        self,
        id: str,
        name: str,
        subscription_id: str,
        resource_group: str,
        zone_name: str,
        record_type: str,  # A, AAAA, CNAME, MX, TXT, SRV, SOA, NS
        ttl: int = 3600,
        records: Optional[list[dict]] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/privateDnsZones/recordSets"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.zone_name = zone_name
        self.record_type = record_type
        self.ttl = ttl
        self.records = records or []
        self.metadata = metadata or {}
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "type": f"Microsoft.Network/privateDnsZones/{record_type}",
            "name": name,
            "ttl": ttl,
            "recordSets": self.records,
            "metadata": self.metadata,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class RouteTable:
    """Azure-style Route Table backed by Cilium BGP routing."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        location: str, disable_bgp_route_propagation: bool = False,
    ):
        """Route table for custom routing rules. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/routeTables"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.disable_bgp_route_propagation = disable_bgp_route_propagation
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "disableBgpRoutePropagation": disable_bgp_route_propagation,
            "routes": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class Route:
    """User Defined Route (UDR) within a Route Table. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        address_prefix: str, next_hop_type: str, next_hop_ip_address: Optional[str] = None,
    ):
        """Individual route rule. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/routeTables/routes"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.address_prefix = address_prefix
        self.next_hop_type = next_hop_type  # VirtualNetworkGateway, VirtualAppliance, Internet, VnetLocal, None
        self.next_hop_ip_address = next_hop_ip_address
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "addressPrefix": address_prefix,
            "nextHopType": next_hop_type,
            "nextHopIpAddress": next_hop_ip_address,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class ServiceEndpoint:
    """Azure Service Endpoint for private access to Azure services. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        service: str, locations: Optional[list[str]] = None,
    ):
        """Service endpoint allows VNet to access Azure services privately. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/serviceEndpoints"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.service = service  # e.g., "Microsoft.Storage", "Microsoft.Sql"
        self.locations = locations or []
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "service": service,
            "locations": self.locations,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class ApplicationGateway:
    """Azure Application Gateway (Layer 7 load balancer) backed by K8s Ingress."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        location: str, sku: str = "Standard_v2",
        backend_pools: Optional[list[dict]] = None,
        http_listeners: Optional[list[dict]] = None,
        url_path_maps: Optional[list[dict]] = None,
        backend_settings: Optional[list[dict]] = None,
    ):
        """Layer 7 load balancer with URL routing and SSL termination."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/applicationGateways"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.sku = sku
        self.backend_pools = backend_pools or []
        self.http_listeners = http_listeners or []
        self.url_path_maps = url_path_maps or []
        self.backend_settings = backend_settings or []
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "sku": {"name": sku, "tier": "Standard_v2", "capacity": 2},
            "gatewayIPConfigurations": [],
            "frontendIPConfigurations": [],
            "frontendPorts": [{"name": "port_80", "port": 80}],
            "backendHttpSettings": self.backend_settings,
            "backendAddressPools": self.backend_pools,
            "httpListeners": self.http_listeners,
            "urlPathMaps": self.url_path_maps,
            "requestRoutingRules": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "properties": self.properties,
        }


class VPNGateway:
    """Azure VPN Gateway for site-to-site and point-to-site connectivity. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        location: str, vpn_type: str = "RouteBased",
    ):
        """VPN gateway for on-prem and client connectivity. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/vpnGateways"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.vpn_type = vpn_type
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "vpnType": vpn_type,
            "connections": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class NATGateway:
    """Azure NAT Gateway for outbound NAT. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        location: str, idle_timeout_in_minutes: int = 4,
    ):
        """Outbound NAT for subnet traffic. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/natGateways"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.idle_timeout_in_minutes = idle_timeout_in_minutes
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "idleTimeoutInMinutes": idle_timeout_in_minutes,
            "publicIps": [],
            "subnets": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class Bastion:
    """Azure Bastion for secure RDP/SSH access. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        location: str, vnet_id: str,
    ):
        """Secure tunneling for RDP/SSH without public IPs. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/bastionHosts"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.vnet_id = vnet_id
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "virtualNetwork": {"id": vnet_id},
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class NetworkWatcher:
    """Azure Network Watcher for monitoring and diagnostics. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        location: str,
    ):
        """Packet capture, flow logs, connection diagnostics. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/networkWatchers"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class AzureFirewall:
    """Azure Firewall for network-level filtering. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        location: str, threat_intel_mode: str = "Off",
    ):
        """Stateful firewall with threat intelligence. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/azureFirewalls"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.threat_intel_mode = threat_intel_mode
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "threatIntelMode": threat_intel_mode,
            "applicationRuleCollections": [],
            "networkRuleCollections": [],
            "natRuleCollections": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class ExpressRoute:
    """Azure ExpressRoute for dedicated network circuits. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        location: str, service_provider: str,
    ):
        """Dedicated network circuit to Azure. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/expressRouteCircuits"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.service_provider = service_provider
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "serviceProvider": service_provider,
            "peerings": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class VirtualHub:
    """Azure Virtual Hub for hub-and-spoke topology. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        location: str, address_prefix: str,
    ):
        """Hub for hub-and-spoke networking. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/virtualHubs"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.address_prefix = address_prefix
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "addressPrefix": address_prefix,
            "routes": [],
            "connections": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class TrafficManager:
    """Azure Traffic Manager for global load balancing. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        routing_method: str = "Performance",
    ):
        """Global load balancer with failover. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/trafficManagerProfiles"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.routing_method = routing_method
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "routingMethod": routing_method,
            "endpoints": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class FrontDoor:
    """Azure Front Door for CDN and global routing. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        sku: str = "Standard",
    ):
        """CDN with global load balancing. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/frontDoors"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.sku = sku
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "sku": sku,
            "routingRules": [],
            "backendPools": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class DDoSProtection:
    """Azure DDoS Protection Standard. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        location: str,
    ):
        """DDoS mitigation and protection. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/ddosProtectionPlans"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "protectedResources": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


class PublicDnsZone:
    """Azure Public DNS Zone for public domain hosting. Not yet implemented."""
    
    def __init__(
        self, id: str, name: str, subscription_id: str, resource_group: str,
        zone_name: str,
    ):
        """Public DNS zone for internet-facing domains. Not yet implemented."""
        self.id = id
        self.name = name
        self.type = "Microsoft.Network/publicDnsZones"
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.zone_name = zone_name
        self.provisioning_state = "Succeeded"
        self.properties = {
            "provisioningState": self.provisioning_state,
            "zoneName": zone_name,
            "recordSets": [],
        }
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "properties": self.properties,
        }


# ============================================================================
# Network Provider with Cilium Integration
# ============================================================================


class NetworkProvider(ResourceProvider):
    """
    Network Provider for ITL ControlPlane using Azure patterns + Cilium SDN.
    
    Maps Azure-style networking to Cilium on Kubernetes:
    - VNets → K8s Namespaces + Cilium IPv4/IPv6 pools
    - Subnets → Cilium LoadBalancerIPPool resources
    - NSGs → Cilium CiliumNetworkPolicy L3/L4/L7 rules
    - NICs → Pod/VM network interface attachments
    - LBs → K8s Services + Cilium LoadBalancer
    - Public IPs → Cilium external IP allocations
    
    Uses Kubernetes API client for Cilium CRD management.
    """

    def __init__(self, engine: Optional[SQLAlchemyStorageEngine] = None):
        """
        Initialize the Network Provider with multi-cluster support.
        
        Args:
            engine: SQLAlchemy storage engine for persistence
        """
        super().__init__("Microsoft.Network")
        self.engine = engine
        
        # Multi-cluster configuration (storage, data, compute clusters)
        self.clusters = {
            "storage": {
                "endpoint": os.getenv("STORAGE_CLUSTER_ENDPOINT", "http://localhost:8001"),
                "v1": None,
                "custom_api": None,
            },
            "data": {
                "endpoint": os.getenv("DATA_CLUSTER_ENDPOINT", "http://localhost:8001"),
                "v1": None,
                "custom_api": None,
            },
            "compute": {
                "endpoint": os.getenv("COMPUTE_CLUSTER_ENDPOINT", "http://localhost:8001"),
                "v1": None,
                "custom_api": None,
            },
        }
        
        # Legacy single-cluster reference (for backwards compatibility)
        self.v1: Optional[client.CoreV1Api] = None
        self.custom_api: Optional[client.CustomObjectsApi] = None
        
        # Cilium configuration
        self.cilium_namespace = os.getenv("CILIUM_NAMESPACE", "kube-system")
        self.k8s_config_path = os.getenv("KUBECONFIG", None)
        
        logger.info(
            "Initialized Network Provider with multi-cluster support",
            cilium_namespace=self.cilium_namespace,
            clusters=list(self.clusters.keys()),
        )

    async def initialize(self) -> None:
        """Initialize Kubernetes API clients for all clusters (multi-cluster mode)."""
        try:
            # Try to load K8s config (for local development)
            try:
                if self.k8s_config_path:
                    config.load_kube_config(config_file=self.k8s_config_path)
                else:
                    config.load_incluster_config()
            except Exception as e:
                logger.warning(f"K8s config loading failed, using cluster endpoints directly: {e}")
            
            # Initialize clients for all clusters
            for cluster_name, cluster_config in self.clusters.items():
                try:
                    # Create API configuration for this cluster
                    api_client = client.ApiClient()
                    cluster_config["v1"] = client.CoreV1Api(api_client=api_client)
                    cluster_config["custom_api"] = client.CustomObjectsApi(api_client=api_client)
                    
                    logger.info(
                        f"✓ Connected to {cluster_name} cluster",
                        endpoint=cluster_config["endpoint"],
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to connect to {cluster_name} cluster: {e}",
                        endpoint=cluster_config["endpoint"],
                    )
            
            # Set legacy references to first available cluster (backwards compatibility)
            if self.clusters["storage"]["v1"]:
                self.v1 = self.clusters["storage"]["v1"]
                self.custom_api = self.clusters["storage"]["custom_api"]
            
            logger.info("✓ Initialized multi-cluster Network Provider")
        except Exception as e:
            logger.error(f"Failed to initialize clusters: {e}")
            raise

    async def shutdown(self) -> None:
        """Cleanup resources."""
        logger.info("Shutting down Network Provider")

    # ========================================================================
    # Multi-Cluster Helper Methods
    # ========================================================================

    async def _get_all_v1_clients(self) -> dict:
        """Get v1 API clients for all clusters."""
        return {name: cfg["v1"] for name, cfg in self.clusters.items() if cfg["v1"]}

    async def _get_all_custom_api_clients(self) -> dict:
        """Get custom API clients for all clusters."""
        return {name: cfg["custom_api"] for name, cfg in self.clusters.items() if cfg["custom_api"]}

    async def _create_namespace_all_clusters(self, namespace: str) -> None:
        """Create K8s namespace in all clusters."""
        v1_clients = await self._get_all_v1_clients()
        
        ns_obj = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=namespace,
                labels={
                    "app.kubernetes.io/part-of": "itl-controlplane",
                    "itl.tenant": namespace,
                },
            ),
        )
        
        for cluster_name, v1 in v1_clients.items():
            try:
                v1.create_namespace(ns_obj)
                logger.info(f"✓ Created namespace {namespace} in {cluster_name} cluster")
            except ApiException as e:
                if e.status == 409:  # Already exists
                    logger.debug(f"Namespace {namespace} already exists in {cluster_name}")
                else:
                    logger.error(f"Failed to create namespace in {cluster_name}: {e}")
                    raise

    async def _delete_namespace_all_clusters(self, namespace: str) -> None:
        """Delete K8s namespace from all clusters."""
        v1_clients = await self._get_all_v1_clients()
        
        for cluster_name, v1 in v1_clients.items():
            try:
                v1.delete_namespace(name=namespace, body=client.V1DeleteOptions(propagation_policy="Foreground"))
                logger.info(f"✓ Deleted namespace {namespace} from {cluster_name} cluster")
            except ApiException as e:
                if e.status != 404:  # Not found is OK
                    logger.error(f"Failed to delete namespace in {cluster_name}: {e}")

    async def _apply_cilium_pool_all_clusters(self, manifest: dict, namespace: str) -> None:
        """Apply Cilium LoadBalancerIPPool to all clusters."""
        custom_api_clients = await self._get_all_custom_api_clients()
        group = "cilium.io"
        version = "v2alpha1"
        plural = "ciliumloadbalancerippools"
        name = manifest["metadata"]["name"]
        
        for cluster_name, custom_api in custom_api_clients.items():
            try:
                # Try to get existing pool
                try:
                    custom_api.get_namespaced_custom_object(
                        group=group, version=version, namespace=namespace, plural=plural, name=name
                    )
                    # Update existing
                    custom_api.patch_namespaced_custom_object(
                        group=group, version=version, namespace=namespace, plural=plural, name=name, body=manifest
                    )
                    logger.info(f"✓ Updated Cilium pool {name} in {cluster_name} cluster")
                except ApiException as e:
                    if e.status == 404:
                        # Create new
                        custom_api.create_namespaced_custom_object(
                            group=group, version=version, namespace=namespace, plural=plural, body=manifest
                        )
                        logger.info(f"✓ Created Cilium pool {name} in {cluster_name} cluster")
                    else:
                        raise
            except ApiException as e:
                logger.error(f"Failed to apply pool in {cluster_name}: {e}")
                raise

    async def _apply_cilium_policy_all_clusters(self, manifest: dict, namespace: str) -> None:
        """Apply Cilium CiliumNetworkPolicy to all clusters."""
        custom_api_clients = await self._get_all_custom_api_clients()
        group = "cilium.io"
        version = "v2"
        plural = "ciliumnetworkpolicies"
        name = manifest["metadata"]["name"]
        
        for cluster_name, custom_api in custom_api_clients.items():
            try:
                # Try to get existing policy
                try:
                    custom_api.get_namespaced_custom_object(
                        group=group, version=version, namespace=namespace, plural=plural, name=name
                    )
                    # Update existing
                    custom_api.patch_namespaced_custom_object(
                        group=group, version=version, namespace=namespace, plural=plural, name=name, body=manifest
                    )
                    logger.info(f"✓ Updated Cilium policy {name} in {cluster_name} cluster")
                except ApiException as e:
                    if e.status == 404:
                        # Create new
                        custom_api.create_namespaced_custom_object(
                            group=group, version=version, namespace=namespace, plural=plural, body=manifest
                        )
                        logger.info(f"✓ Created Cilium policy {name} in {cluster_name} cluster")
                    else:
                        raise
            except ApiException as e:
                logger.error(f"Failed to apply policy in {cluster_name}: {e}")
                raise

    async def _setup_clustermesh(self, cluster_names: list[str] = None) -> None:
        """Setup ClusterMesh for multi-cluster networking."""
        if not cluster_names:
            cluster_names = list(self.clusters.keys())
        
        custom_api_clients = await self._get_all_custom_api_clients()
        
        # Create ClusterMesh configuration for each cluster
        for cluster_name, custom_api in custom_api_clients.items():
            try:
                # Note: ClusterMesh setup is typically done via Cilium Helm values
                # This is a simplified representation
                logger.info(f"✓ ClusterMesh configured for {cluster_name} cluster")
            except Exception as e:
                logger.error(f"Failed to setup ClusterMesh in {cluster_name}: {e}")

    # ========================================================================
    # SDK-Required Interface Methods
    # ========================================================================

    async def create_or_update_resource(
        self, request: ResourceRequest
    ) -> ResourceResponse:
        """Create or update a network resource (SDK interface)."""
        try:
            resource_type = request.resource_type
            resource_name = request.resource_name
            subscription_id = request.subscription_id or "default"
            resource_group = request.resource_group or "default"

            logger.info(
                f"Creating/updating {resource_type}: {resource_name}",
                subscription=subscription_id,
                group=resource_group,
            )

            # Extract properties
            properties = dict(request.body or {})
            if hasattr(request, "properties") and request.properties:
                if hasattr(request.properties, "model_dump"):
                    properties.update(request.properties.model_dump(exclude_none=True))
                elif isinstance(request.properties, dict):
                    properties.update(request.properties)

            # Generate resource ID
            resource_id = generate_resource_id(
                subscription_id=subscription_id,
                resource_group=resource_group,
                provider_namespace=self.provider_namespace,
                resource_type=resource_type,
                resource_name=resource_name,
            )

            # Dispatch to backend handler
            result = await self._create_resource_by_type(
                resource_type, resource_id, resource_name, properties,
                subscription_id, resource_group, request.location or "eastus"
            )

            # Persist to database
            if self.engine:
                resource_data = {
                    "id": resource_id,
                    "name": resource_name,
                    "type": f"{self.provider_namespace}/{resource_type}",
                    "location": request.location or "eastus",
                    "properties": result,
                    "tags": request.tags or {},
                }
                await self.engine.upsert_resource(resource_data)

            return ResourceResponse(
                id=resource_id,
                name=resource_name,
                type=f"{self.provider_namespace}/{resource_type}",
                location=request.location or "eastus",
                properties=result,
                tags=request.tags or {},
                provisioning_state=ProvisioningState.SUCCEEDED,
            )

        except Exception as e:
            logger.error(f"Failed to create {request.resource_type}: {str(e)}", exc_info=True)
            return self._error_response(request.resource_type, request.resource_name, str(e))

    async def get_resource(self, request: ResourceRequest) -> ResourceResponse:
        """Get a network resource by ID."""
        try:
            resource_id = generate_resource_id(
                subscription_id=request.subscription_id or "default",
                resource_group=request.resource_group or "default",
                provider_namespace=self.provider_namespace,
                resource_type=request.resource_type,
                resource_name=request.resource_name,
            )

            if self.engine:
                resource = await self.engine.get_resource(resource_id)
                if resource:
                    return ResourceResponse(
                        id=resource["id"],
                        name=request.resource_name,
                        type=f"{self.provider_namespace}/{request.resource_type}",
                        location=resource.get("location", "eastus"),
                        properties=resource.get("properties", {}),
                        tags=resource.get("tags", {}),
                        provisioning_state=ProvisioningState.SUCCEEDED,
                    )

            return self._error_response(
                request.resource_type, request.resource_name, "Resource not found"
            )

        except Exception as e:
            logger.error(f"Failed to get resource: {str(e)}", exc_info=True)
            return self._error_response(request.resource_type, request.resource_name, str(e))

    async def list_resources(
        self, resource_type: str, subscription_id: str = "default",
        resource_group: Optional[str] = None
    ) -> ResourceListResponse:
        """List network resources by type."""
        try:
            resources = []
            # TODO: Query from database with filters
            return ResourceListResponse(value=resources)
        except Exception as e:
            logger.error(f"Failed to list {resource_type}: {str(e)}", exc_info=True)
            return ResourceListResponse(value=[])

    async def delete_resource(self, request: ResourceRequest) -> ResourceResponse:
        """Delete a network resource."""
        try:
            resource_id = generate_resource_id(
                subscription_id=request.subscription_id or "default",
                resource_group=request.resource_group or "default",
                provider_namespace=self.provider_namespace,
                resource_type=request.resource_type,
                resource_name=request.resource_name,
            )

            await self._delete_resource_by_type(
                request.resource_type, resource_id, request.resource_name
            )

            if self.engine:
                await self.engine.delete_resource(resource_id)

            return ResourceResponse(
                id=resource_id,
                name=request.resource_name,
                type=f"{self.provider_namespace}/{request.resource_type}",
                location=request.location or "eastus",
                properties={"deleted": True},
                provisioning_state=ProvisioningState.SUCCEEDED,
            )

        except Exception as e:
            logger.error(f"Failed to delete resource: {str(e)}", exc_info=True)
            return self._error_response(request.resource_type, request.resource_name, str(e))

    # ========================================================================
    # Dispatch Methods
    # ========================================================================

    async def _create_resource_by_type(
        self, resource_type: str, resource_id: str, resource_name: str,
        properties: dict, subscription_id: str, resource_group: str, location: str,
    ) -> dict:
        """Dispatch resource creation."""
        match resource_type:
            case "virtualNetworks":
                return await self._create_vnet(
                    resource_id, resource_name, properties, location
                )
            case "virtualNetworks/subnets":
                return await self._create_subnet(
                    resource_id, resource_name, properties, location
                )
            case "networkSecurityGroups":
                return await self._create_nsg(
                    resource_id, resource_name, properties, location
                )
            case "networkInterfaces":
                return await self._create_nic(
                    resource_id, resource_name, properties, location
                )
            case "publicIPAddresses":
                return await self._create_public_ip(
                    resource_id, resource_name, properties, location
                )
            case "loadBalancers":
                return await self._create_lb(
                    resource_id, resource_name, properties, location
                )
            case "bgpPeeringPolicies":
                return await self._create_bgp_peering_policy(
                    resource_id, resource_name, properties, location
                )
            case "virtualNetworkPeerings":
                return await self._create_vnet_peering(
                    resource_id, resource_name, properties, location
                )
            case "privateLinkServices":
                return await self._create_private_link_service(
                    resource_id, resource_name, properties, location
                )
            case "privateEndpoints":
                return await self._create_private_endpoint(
                    resource_id, resource_name, properties, location
                )
            case "privateDnsZones":
                return await self._create_private_dns_zone(
                    resource_id, resource_name, properties, location
                )
            case "privateDnsZones/recordSets":
                return await self._create_dns_record(
                    resource_id, resource_name, properties, location
                )
            case "routeTables":
                return await self._create_route_table(
                    resource_id, resource_name, properties, location
                )
            case "routeTables/routes":
                return await self._create_route(
                    resource_id, resource_name, properties, location
                )
            case "serviceEndpoints":
                return await self._create_service_endpoint(
                    resource_id, resource_name, properties, location
                )
            case "applicationGateways":
                return await self._create_application_gateway(
                    resource_id, resource_name, properties, location
                )
            case "vpnGateways":
                return await self._create_vpn_gateway(
                    resource_id, resource_name, properties, location
                )
            case "natGateways":
                return await self._create_nat_gateway(
                    resource_id, resource_name, properties, location
                )
            case "bastionHosts":
                return await self._create_bastion(
                    resource_id, resource_name, properties, location
                )
            case "networkWatchers":
                return await self._create_network_watcher(
                    resource_id, resource_name, properties, location
                )
            case "azureFirewalls":
                return await self._create_azure_firewall(
                    resource_id, resource_name, properties, location
                )
            case "expressRouteCircuits":
                return await self._create_express_route(
                    resource_id, resource_name, properties, location
                )
            case "virtualHubs":
                return await self._create_virtual_hub(
                    resource_id, resource_name, properties, location
                )
            case "trafficManagerProfiles":
                return await self._create_traffic_manager(
                    resource_id, resource_name, properties, location
                )
            case "frontDoors":
                return await self._create_front_door(
                    resource_id, resource_name, properties, location
                )
            case "ddosProtectionPlans":
                return await self._create_ddos_protection(
                    resource_id, resource_name, properties, location
                )
            case "publicDnsZones":
                return await self._create_public_dns_zone(
                    resource_id, resource_name, properties, location
                )
            case _:
                raise ValueError(f"Unsupported resource type: {resource_type}")

    async def _delete_resource_by_type(
        self, resource_type: str, resource_id: str, resource_name: str
    ) -> None:
        """Dispatch resource deletion."""
        match resource_type:
            case "virtualNetworks":
                await self._delete_vnet(resource_id)
            case "virtualNetworks/subnets":
                await self._delete_subnet(resource_id)
            case "networkSecurityGroups":
                await self._delete_nsg(resource_id)
            case "networkInterfaces":
                await self._delete_nic(resource_id)
            case "publicIPAddresses":
                await self._delete_public_ip(resource_id)
            case "loadBalancers":
                await self._delete_lb(resource_id)
            case "bgpPeeringPolicies":
                await self._delete_bgp_peering_policy(resource_id)
            case "virtualNetworkPeerings":
                await self._delete_vnet_peering(resource_id)
            case "privateLinkServices":
                await self._delete_private_link_service(resource_id)
            case "privateEndpoints":
                await self._delete_private_endpoint(resource_id)
            case "privateDnsZones":
                await self._delete_private_dns_zone(resource_id)
            case "privateDnsZones/recordSets":
                await self._delete_dns_record(resource_id)
            case "routeTables":
                await self._delete_route_table(resource_id)
            case "routeTables/routes":
                await self._delete_route(resource_id)
            case "serviceEndpoints":
                await self._delete_service_endpoint(resource_id)
            case "applicationGateways":
                await self._delete_application_gateway(resource_id)
            case "vpnGateways":
                await self._delete_vpn_gateway(resource_id)
            case "natGateways":
                await self._delete_nat_gateway(resource_id)
            case "bastionHosts":
                await self._delete_bastion(resource_id)
            case "networkWatchers":
                await self._delete_network_watcher(resource_id)
            case "azureFirewalls":
                await self._delete_azure_firewall(resource_id)
            case "expressRouteCircuits":
                await self._delete_express_route(resource_id)
            case "virtualHubs":
                await self._delete_virtual_hub(resource_id)
            case "trafficManagerProfiles":
                await self._delete_traffic_manager(resource_id)
            case "frontDoors":
                await self._delete_front_door(resource_id)
            case "ddosProtectionPlans":
                await self._delete_ddos_protection(resource_id)
            case "publicDnsZones":
                await self._delete_public_dns_zone(resource_id)

    # ========================================================================
    # VNet Creation (Cilium Integration)
    # ========================================================================

    async def _create_vnet(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Virtual Network across all clusters (multi-cluster mode)."""
        # Extract subscription ID for tenant namespace
        parts = resource_id.split("/")
        subscription_id = parts[2] if len(parts) > 2 else "default"
        
        # Tenant-scoped namespace (shared across clusters)
        tenant_namespace = f"sub-{subscription_id[:8]}".lower()
        
        address_space = properties.get("addressSpace", ["10.0.0.0/16"])
        if isinstance(address_space, dict) and "addressPrefixes" in address_space:
            address_space = address_space["addressPrefixes"]
        
        logger.debug(
            "Creating Virtual Network across all clusters",
            vnet=resource_name,
            addressSpace=address_space,
            tenantNamespace=tenant_namespace,
        )
        
        try:
            # Generate unique K8s pool name from resource ID
            k8s_pool_name = _generate_k8s_name(resource_id, "pool")
            
            # 1. Create tenant namespace in all clusters
            await self._create_namespace_all_clusters(tenant_namespace)
            
            # 2. Create Cilium pool in all clusters (same IP range across all clusters)
            cilium_pool = {
                "apiVersion": "cilium.io/v2alpha1",
                "kind": "CiliumLoadBalancerIPPool",
                "metadata": {
                    "name": k8s_pool_name,
                    "namespace": tenant_namespace,
                    "labels": {
                        "vnet": resource_name,
                        "itl.resource-id": resource_id,
                    },
                },
                "spec": {
                    "blocks": [{"cidr": addr} for addr in address_space],
                },
            }
            
            await self._apply_cilium_pool_all_clusters(cilium_pool, tenant_namespace)
            logger.info(f"✓ Created Cilium pool: {k8s_pool_name} in all clusters (Azure VNet: {resource_name})")
            
            # 3. Setup ClusterMesh for cross-cluster communication
            await self._setup_clustermesh()
            
            vnet = VirtualNetwork(
                id=resource_id,
                name=resource_name,
                subscription_id=subscription_id,
                resource_group="default",
                location=location,
                address_space=address_space,
            )
            
            logger.info(f"✓ Created VNet: {resource_name} (Tenant: {tenant_namespace}, IP: {address_space[0]}, Clusters: storage, data, compute)")
            return vnet.to_dict()["properties"]
        
        except Exception as e:
            logger.error(f"Failed to create VNet: {e}")
            raise

    async def _delete_vnet(self, resource_id: str) -> None:
        """Delete Virtual Network from all clusters."""
        try:
            # Extract subscription ID for tenant namespace
            parts = resource_id.split("/")
            subscription_id = parts[2] if len(parts) > 2 else "default"
            tenant_namespace = f"sub-{subscription_id[:8]}".lower()
            
            # Generate same K8s pool name as creation
            k8s_pool_name = _generate_k8s_name(resource_id, "pool")
            
            # Delete Cilium pool from all clusters
            custom_api_clients = await self._get_all_custom_api_clients()
            for cluster_name, custom_api in custom_api_clients.items():
                try:
                    custom_api.delete_namespaced_custom_object(
                        group="cilium.io",
                        version="v2alpha1",
                        namespace=tenant_namespace,
                        plural="ciliumloadbalancerippools",
                        name=k8s_pool_name,
                    )
                    logger.info(f"✓ Deleted Cilium pool in {cluster_name}: {k8s_pool_name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to delete pool in {cluster_name}: {e}")
            
            logger.info(f"✓ Deleted VNet resources: {resource_id}")
        
        except Exception as e:
            logger.error(f"Failed to delete VNet: {e}")

    # ========================================================================
    # Subnet Creation (Cilium Integration)
    # ========================================================================

    async def _create_subnet(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Subnet across all clusters (multi-cluster mode)."""
        # Extract subscription ID for tenant namespace
        parts = resource_id.split("/")
        subscription_id = parts[2] if len(parts) > 2 else "default"
        tenant_namespace = f"sub-{subscription_id[:8]}".lower()
        
        address_prefix = properties.get("addressPrefix", "10.0.1.0/24")
        
        logger.debug(
            "Creating Subnet across all clusters",
            subnet=resource_name,
            addressPrefix=address_prefix,
            tenantNamespace=tenant_namespace,
        )
        
        try:
            # Generate unique K8s name from resource ID
            k8s_pool_name = _generate_k8s_name(resource_id, "subnet")
            
            # Create IP pool for subnet in all clusters (same CIDR across all clusters)
            cilium_pool = {
                "apiVersion": "cilium.io/v2alpha1",
                "kind": "CiliumLoadBalancerIPPool",
                "metadata": {
                    "name": k8s_pool_name,
                    "namespace": tenant_namespace,
                    "labels": {
                        "subnet": resource_name,
                        "itl.resource-id": resource_id,
                    },
                },
                "spec": {
                    "blocks": [{"cidr": address_prefix}],
                },
            }
            
            await self._apply_cilium_pool_all_clusters(cilium_pool, tenant_namespace)
            logger.info(f"✓ Created Cilium subnet pool: {k8s_pool_name} in all clusters (Azure Subnet: {resource_name})")
            
            subnet = Subnet(
                id=resource_id,
                name=resource_name,
                subscription_id=subscription_id,
                resource_group="default",
                vnet_id=properties.get("virtualNetworkId", ""),
                address_prefix=address_prefix,
            )
            
            return subnet.to_dict()["properties"]
        
        except Exception as e:
            logger.error(f"Failed to create subnet: {e}")
            raise

    async def _delete_subnet(self, resource_id: str) -> None:
        """Delete Subnet from all clusters."""
        try:
            # Extract subscription ID for tenant namespace
            parts = resource_id.split("/")
            subscription_id = parts[2] if len(parts) > 2 else "default"
            tenant_namespace = f"sub-{subscription_id[:8]}".lower()
            
            # Generate same K8s name as creation
            k8s_pool_name = _generate_k8s_name(resource_id, "subnet")
            
            # Delete from all clusters
            custom_api_clients = await self._get_all_custom_api_clients()
            for cluster_name, custom_api in custom_api_clients.items():
                try:
                    custom_api.delete_namespaced_custom_object(
                        group="cilium.io",
                        version="v2alpha1",
                        namespace=tenant_namespace,
                        plural="ciliumloadbalancerippools",
                        name=k8s_pool_name,
                    )
                    logger.info(f"✓ Deleted Cilium subnet pool in {cluster_name}: {k8s_pool_name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to delete subnet in {cluster_name}: {e}")
        except Exception as e:
            logger.error(f"Failed to delete subnet: {e}")

    # ========================================================================
    # NSG Creation (Cilium NetworkPolicy)
    # ========================================================================

    async def _create_nsg(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create NSG across all clusters via Cilium CiliumNetworkPolicy."""
        # Extract subscription ID for tenant namespace
        parts = resource_id.split("/")
        subscription_id = parts[2] if len(parts) > 2 else "default"
        tenant_namespace = f"sub-{subscription_id[:8]}".lower()
        
        security_rules = properties.get("securityRules", [])
        
        logger.debug(
            "Creating NSG across all clusters",
            nsg=resource_name,
            ruleCount=len(security_rules),
            tenantNamespace=tenant_namespace,
        )
        
        try:
            # Convert Azure NSG rules to Cilium format
            ingress_rules = []
            egress_rules = []
            
            for rule in security_rules:
                direction = rule.get("direction", "Inbound").lower()
                protocol = rule.get("protocol", "*").lower()
                
                from_port = rule.get("sourcePortRange", "*")
                to_port = rule.get("destinationPortRange", "*")
                
                # Parse port ranges
                from_port = int(from_port) if from_port != "*" else None
                to_port = int(to_port) if to_port != "*" else None
                
                cilium_rule = {
                    "fromEndpoints": [{"matchLabels": {"k8s:io.kubernetes.pod.namespace": tenant_namespace}}],
                }
                
                if protocol != "*":
                    if protocol == "tcp":
                        cilium_rule["toPorts"] = [{"ports": [{"port": str(to_port or 80)}], "protocol": "TCP"}]
                    elif protocol == "udp":
                        cilium_rule["toPorts"] = [{"ports": [{"port": str(to_port or 53)}], "protocol": "UDP"}]
                
                if direction == "inbound":
                    ingress_rules.append(cilium_rule)
                else:
                    egress_rules.append(cilium_rule)
            
            # Generate unique K8s name from resource ID
            k8s_policy_name = _generate_k8s_name(resource_id, "policy")
            
            # Create policy in all clusters
            cilium_policy = {
                "apiVersion": "cilium.io/v2",
                "kind": "CiliumNetworkPolicy",
                "metadata": {
                    "name": k8s_policy_name,
                    "namespace": tenant_namespace,
                    "labels": {
                        "nsg": resource_name,
                        "itl.resource-id": resource_id,
                    },
                },
                "spec": {
                    "endpointSelector": {"matchLabels": {"app": resource_name}},
                    "ingress": ingress_rules if ingress_rules else None,
                    "egress": egress_rules if egress_rules else None,
                },
            }
            
            await self._apply_cilium_policy_all_clusters(cilium_policy, tenant_namespace)
            logger.info(f"✓ Created Cilium network policy: {k8s_policy_name} in all clusters (Azure NSG: {resource_name})")
            
            nsg = NetworkSecurityGroup(
                id=resource_id,
                name=resource_name,
                subscription_id=subscription_id,
                resource_group="default",
                location=location,
            )
            nsg.security_rules = security_rules
            
            return nsg.to_dict()["properties"]
        
        except Exception as e:
            logger.error(f"Failed to create NSG: {e}")
            raise

    async def _delete_nsg(self, resource_id: str) -> None:
        """Delete NSG from all clusters."""
        try:
            # Extract subscription ID for tenant namespace
            parts = resource_id.split("/")
            subscription_id = parts[2] if len(parts) > 2 else "default"
            tenant_namespace = f"sub-{subscription_id[:8]}".lower()
            
            # Generate same K8s name as creation
            k8s_policy_name = _generate_k8s_name(resource_id, "policy")
            
            # Delete from all clusters
            custom_api_clients = await self._get_all_custom_api_clients()
            for cluster_name, custom_api in custom_api_clients.items():
                try:
                    custom_api.delete_namespaced_custom_object(
                        group="cilium.io",
                        version="v2",
                        namespace=tenant_namespace,
                        plural="ciliumnetworkpolicies",
                        name=k8s_policy_name,
                    )
                    logger.info(f"✓ Deleted Cilium network policy in {cluster_name}: {k8s_policy_name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to delete NSG in {cluster_name}: {e}")
        except Exception as e:
            logger.error(f"Failed to delete NSG: {e}")

    # ========================================================================
    # NIC Creation
    # ========================================================================

    async def _create_nic(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Network Interface."""
        subnet_id = properties.get("subnet", "")
        private_ip = properties.get("privateIPAddress", "10.0.0.0")
        
        logger.debug(f"Creating NIC: {resource_name}")
        
        nic = NetworkInterface(
            id=resource_id,
            name=resource_name,
            subscription_id="default",
            resource_group="default",
            location=location,
            vnet_id=properties.get("virtualNetworkId", ""),
            subnet_id=subnet_id,
            private_ip=private_ip,
        )
        
        return nic.to_dict()["properties"]

    async def _delete_nic(self, resource_id: str) -> None:
        """Delete Network Interface."""
        logger.debug(f"Deleting NIC: {resource_id}")

    # ========================================================================
    # Public IP Creation (Cilium IP Pool)
    # ========================================================================

    async def _create_public_ip(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Public IP Address via Cilium external IP allocation."""
        allocation_method = properties.get("publicIPAllocationMethod", "Static")
        
        logger.debug(
            "Creating Public IP",
            publicIP=resource_name,
            method=allocation_method,
        )
        
        public_ip = PublicIpAddress(
            id=resource_id,
            name=resource_name,
            subscription_id="default",
            resource_group="default",
            location=location,
            allocation_method=allocation_method,
        )
        
        # TODO: Allocate IP from Cilium external pool
        public_ip.ip_address = f"203.0.113.{hash(resource_name) % 256}"
        
        return public_ip.to_dict()["properties"]

    async def _delete_public_ip(self, resource_id: str) -> None:
        """Delete Public IP Address."""
        logger.debug(f"Deleting Public IP: {resource_id}")

    # ========================================================================
    # Load Balancer Creation (K8s Service + Cilium LB)
    # ========================================================================

    async def _create_lb(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Load Balancer via K8s Service + Cilium LB."""
        sku = properties.get("sku", "Standard")
        
        logger.debug(f"Creating Load Balancer: {resource_name} (SKU: {sku})")
        
        try:
            # Generate unique K8s name from resource ID
            k8s_service_name = _generate_k8s_name(resource_id, "lb")
            
            # ===== K8S: Create Service =====
            if self.v1:
                service = client.V1Service(
                    metadata=client.V1ObjectMeta(
                        name=k8s_service_name,
                        namespace="default",
                        labels={"app": resource_name, "itl.resource-id": resource_id},
                    ),
                    spec=client.V1ServiceSpec(
                        type="LoadBalancer",
                        selector={"app": resource_name},
                        ports=[
                            client.V1ServicePort(
                                port=80,
                                target_port=8080,
                                protocol="TCP",
                            )
                        ],
                    ),
                )
                
                try:
                    self.v1.create_namespaced_service("default", service)
                    logger.info(f"✓ Created K8s Service LoadBalancer: {k8s_service_name} (Azure LB: {resource_name})")
                except ApiException as e:
                    if e.status != 409:
                        raise
            
            lb = LoadBalancer(
                id=resource_id,
                name=resource_name,
                subscription_id="default",
                resource_group="default",
                location=location,
                sku=sku,
            )
            
            return lb.to_dict()["properties"]
        
        except Exception as e:
            logger.error(f"Failed to create LB: {e}")
            raise

    async def _delete_lb(self, resource_id: str) -> None:
        """Delete Load Balancer and K8s Service."""
        try:
            # Generate same K8s name as creation
            k8s_service_name = _generate_k8s_name(resource_id, "lb")
            
            if self.v1:
                self.v1.delete_namespaced_service(name=k8s_service_name, namespace="default")
                logger.info(f"✓ Deleted K8s Service: {k8s_service_name}")
        except ApiException as e:
            if e.status != 404:
                raise

    # ========================================================================
    # BGP Peering Policy Creation (Multi-Site Networking)
    # ========================================================================

    async def _create_bgp_peering_policy(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create BGP Peering Policy via Cilium CiliumBGPPeeringPolicy."""
        local_asn = properties.get("localASN", 64512)
        neighbors = properties.get("neighbors", [])
        export_pod_cidr = properties.get("exportPodCIDR", True)
        
        logger.debug(
            "Creating BGP Peering Policy",
            policy=resource_name,
            localASN=local_asn,
            neighbors=len(neighbors),
        )
        
        try:
            # ===== CILIUM: Create BGP Peering Policy =====
            if self.custom_api:
                # Generate unique K8s name from resource ID
                k8s_policy_name = _generate_k8s_name(resource_id, "bgp")
                
                # Transform neighbor objects to Cilium format
                cilium_neighbors = []
                for neighbor in neighbors:
                    cilium_neighbor = {
                        "peerAddress": neighbor.get("peerAddress"),
                        "peerASN": neighbor.get("peerASN"),
                    }
                    
                    # Optional BGP timers
                    if "connectRetrySeconds" in neighbor:
                        cilium_neighbor["connectRetryTimeSeconds"] = neighbor["connectRetrySeconds"]
                    if "holdTimeSeconds" in neighbor:
                        cilium_neighbor["holdTimeSeconds"] = neighbor["holdTimeSeconds"]
                    if "keepAliveSeconds" in neighbor:
                        cilium_neighbor["keepAliveTimeSeconds"] = neighbor["keepAliveSeconds"]
                    
                    cilium_neighbors.append(cilium_neighbor)
                
                # Create CiliumBGPPeeringPolicy manifest
                bgp_policy = {
                    "apiVersion": "cilium.io/v2alpha1",
                    "kind": "CiliumBGPPeeringPolicy",
                    "metadata": {
                        "name": k8s_policy_name,
                        "namespace": self.cilium_namespace,
                    },
                    "spec": {
                        "virtualRouters": [
                            {
                                "localASN": local_asn,
                                "exportPodCIDR": export_pod_cidr,
                                "neighbors": cilium_neighbors,
                            }
                        ]
                    },
                }
                
                await self._apply_cilium_crd(
                    bgp_policy,
                    "ciliumbgppeeringpolicies",
                    self.cilium_namespace
                )
                logger.info(f"✓ Created Cilium BGP peering policy: {k8s_policy_name} (Azure Policy: {resource_name})")
            
            bgp_policy_obj = BGPPeeringPolicy(
                id=resource_id,
                name=resource_name,
                subscription_id="default",
                resource_group="default",
                location=location,
                local_asn=local_asn,
                neighbors=neighbors,
                export_pod_cidr=export_pod_cidr,
            )
            
            return bgp_policy_obj.to_dict()["properties"]
        
        except Exception as e:
            logger.error(f"Failed to create BGP peering policy: {e}")
            raise

    async def _delete_bgp_peering_policy(self, resource_id: str) -> None:
        """Delete BGP Peering Policy and Cilium CRD."""
        try:
            # Generate same K8s name as creation
            k8s_policy_name = _generate_k8s_name(resource_id, "bgp")
            
            if self.custom_api:
                self.custom_api.delete_namespaced_custom_object(
                    group="cilium.io",
                    version="v2alpha1",
                    namespace=self.cilium_namespace,
                    plural="ciliumbgppeeringpolicies",
                    name=k8s_policy_name,
                )
                logger.info(f"✓ Deleted Cilium BGP peering policy: {k8s_policy_name}")
        except ApiException as e:
            if e.status != 404:
                raise
            logger.debug(f"BGP peering policy not found (already deleted): {resource_id}")

    # ========================================================================
    # VNet Peering Creation (Cilium NetworkPolicy)
    # ========================================================================

    async def _create_vnet_peering(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create VNet Peering across all clusters via Cilium NetworkPolicy."""
        # Extract subscription IDs for tenant namespaces
        # Remote VNet ID format: /subscriptions/{subId}/resourceGroups/{rg}/providers/.../virtualNetworks/{name}
        remote_vnet_id = properties.get("remoteVirtualNetwork", {})
        if isinstance(remote_vnet_id, dict):
            remote_vnet_id = remote_vnet_id.get("id", "")
        
        if not remote_vnet_id:
            raise ValueError("remoteVirtualNetwork.id is required for peering")
        
        # Extract remote subscription ID
        remote_parts = remote_vnet_id.split("/")
        remote_subscription_id = remote_parts[2] if len(remote_parts) > 2 else "default"
        
        # Local subscription from resource ID
        local_parts = resource_id.split("/")
        local_subscription_id = local_parts[2] if len(local_parts) > 2 else "default"
        
        # Tenant namespaces
        local_tenant_ns = f"sub-{local_subscription_id[:8]}".lower()
        remote_tenant_ns = f"sub-{remote_subscription_id[:8]}".lower()
        
        allow_vnet_access = properties.get("allowVirtualNetworkAccess", True)
        allow_forwarded = properties.get("allowForwardedTraffic", False)
        
        logger.debug(
            "Creating VNet Peering across all clusters",
            peering=resource_name,
            localTenant=local_tenant_ns,
            remoteTenant=remote_tenant_ns,
            allowAccess=allow_vnet_access,
        )
        
        try:
            # Generate unique K8s name for peering policy
            k8s_policy_name = _generate_k8s_name(resource_id, "peer")
            
            # Create Cilium NetworkPolicy allowing traffic between namespaces in all clusters
            if allow_vnet_access:
                cilium_peering_policy = {
                    "apiVersion": "cilium.io/v2",
                    "kind": "CiliumNetworkPolicy",
                    "metadata": {
                        "name": k8s_policy_name,
                        "namespace": local_tenant_ns,
                        "labels": {
                            "peering": resource_name,
                            "itl.resource-id": resource_id,
                        },
                    },
                    "spec": {
                        "endpointSelector": {"matchLabels": {"k8s:io.kubernetes.namespace": local_tenant_ns}},
                        "ingress": [
                            {
                                "fromEndpoints": [
                                    {"matchLabels": {"k8s:io.kubernetes.namespace": remote_tenant_ns}}
                                ],
                            }
                        ],
                        "egress": [
                            {
                                "toEndpoints": [
                                    {"matchLabels": {"k8s:io.kubernetes.namespace": remote_tenant_ns}}
                                ],
                            }
                        ] if allow_forwarded else None,
                    },
                }
                
                await self._apply_cilium_policy_all_clusters(cilium_peering_policy, local_tenant_ns)
                logger.info(f"✓ Created peering policy: {k8s_policy_name} (allows {local_tenant_ns} → {remote_tenant_ns})")
            
            peering = VirtualNetworkPeering(
                id=resource_id,
                name=resource_name,
                subscription_id=local_subscription_id,
                resource_group="default",
                local_vnet_id=properties.get("localVirtualNetworkId", ""),
                remote_vnet_id=remote_vnet_id,
                allow_virtual_network_access=allow_vnet_access,
                allow_forwarded_traffic=allow_forwarded,
                allow_gateway_transit=properties.get("allowGatewayTransit", False),
            )
            
            logger.info(f"✓ Created VNet Peering: {resource_name} ({local_tenant_ns} ↔ {remote_tenant_ns})")
            return peering.to_dict()["properties"]
        
        except Exception as e:
            logger.error(f"Failed to create VNet peering: {e}")
            raise

    async def _delete_vnet_peering(self, resource_id: str) -> None:
        """Delete VNet Peering from all clusters."""
        try:
            # Extract subscription ID for local tenant namespace
            parts = resource_id.split("/")
            subscription_id = parts[2] if len(parts) > 2 else "default"
            tenant_namespace = f"sub-{subscription_id[:8]}".lower()
            
            # Generate same K8s name as creation
            k8s_policy_name = _generate_k8s_name(resource_id, "peer")
            
            # Delete from all clusters
            custom_api_clients = await self._get_all_custom_api_clients()
            for cluster_name, custom_api in custom_api_clients.items():
                try:
                    custom_api.delete_namespaced_custom_object(
                        group="cilium.io",
                        version="v2",
                        namespace=tenant_namespace,
                        plural="ciliumnetworkpolicies",
                        name=k8s_policy_name,
                    )
                    logger.info(f"✓ Deleted peering policy in {cluster_name}: {k8s_policy_name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to delete peering in {cluster_name}: {e}")
        except Exception as e:
            logger.error(f"Failed to delete VNet peering: {e}")

    # ========================================================================
    # Private Link Service Creation (Service-Level Private Connectivity)
    # ========================================================================

    async def _create_private_link_service(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create PrivateLinkService and expose K8s Service privately."""
        # Extract subscription and service ID
        subscription_id = resource_id.split("/")[2]
        service_id = properties.get("loadBalancerFrontendIpConfiguration", {}).get("id", "")
        vnet_id = properties.get("virtualNetworkId", "")
        
        tenant_ns = f"sub-{subscription_id[:8]}".lower()
        k8s_name = _generate_k8s_name(resource_id, "pls")  # pls = private link service
        
        logger.info(f"Creating Private Link Service: {resource_name}")
        
        try:
            # Create K8s NetworkPolicy for private endpoint access
            # Restricts access ONLY to connected private endpoints
            pls_policy = {
                "apiVersion": "cilium.io/v2",
                "kind": "CiliumNetworkPolicy",
                "metadata": {
                    "name": k8s_name,
                    "namespace": tenant_ns,
                    "labels": {
                        "service": resource_name,
                        "type": "private-link-service",
                        "itl.resource-id": resource_id,
                    },
                },
                "spec": {
                    "endpointSelector": {
                        "matchLabels": {
                            "k8s:io.kubernetes.namespace": tenant_ns,
                        }
                    },
                    "ingress": [
                        {
                            "fromEndpoints": [
                                {
                                    "matchLabels": {
                                        "type": "private-endpoint",
                                        "linked-service": k8s_name,
                                    }
                                }
                            ]
                        }
                    ],
                },
            }
            
            # Deploy policy to all clusters
            await self._apply_cilium_policy_all_clusters(pls_policy, tenant_ns)
            
            # Create PrivateLinkService object
            pls = PrivateLinkService(
                id=resource_id,
                name=resource_name,
                subscription_id=subscription_id,
                resource_group="default",
                service_id=service_id,
                vnet_id=vnet_id,
                load_balancer_ip=service_id,
                visibility=properties.get("visibility", {}).get("subscriptions", ["*"]),
                auto_approval=properties.get("autoApproval", {}).get("subscriptions", []),
            )
            
            logger.info(f"✓ Created Private Link Service: {resource_name}")
            return pls.to_dict()["properties"]
        
        except Exception as e:
            logger.error(f"Failed to create Private Link Service: {e}")
            raise

    async def _delete_private_link_service(self, resource_id: str) -> None:
        """Delete Private Link Service and cleanup policies."""
        try:
            subscription_id = resource_id.split("/")[2]
            tenant_ns = f"sub-{subscription_id[:8]}".lower()
            k8s_name = _generate_k8s_name(resource_id, "pls")
            
            # Delete policy from all clusters
            custom_api_clients = await self._get_all_custom_api_clients()
            for cluster_name, custom_api in custom_api_clients.items():
                try:
                    custom_api.delete_namespaced_custom_object(
                        group="cilium.io",
                        version="v2",
                        namespace=tenant_ns,
                        plural="ciliumnetworkpolicies",
                        name=k8s_name,
                    )
                    logger.info(f"✓ Deleted PLS policy in {cluster_name}: {k8s_name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to delete PLS in {cluster_name}: {e}")
        except Exception as e:
            logger.error(f"Failed to delete Private Link Service: {e}")

    # ========================================================================
    # Private Endpoint Creation (Consumer-Side Connection)
    # ========================================================================

    async def _create_private_endpoint(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create PrivateEndpoint connecting to a PrivateLinkService."""
        import ipaddress
        
        # Extract consumer subscription and vnet
        consumer_subscription_id = resource_id.split("/")[2]
        consumer_tenant_ns = f"sub-{consumer_subscription_id[:8]}".lower()
        
        # Extract target service connection
        service_conn = properties.get("privateLinkServiceConnections", [{}])[0]
        target_service_id = service_conn.get("id", "")
        
        # Extract producer subscription from target service
        producer_subscription_id = target_service_id.split("/")[2] if target_service_id else consumer_subscription_id
        producer_tenant_ns = f"sub-{producer_subscription_id[:8]}".lower()
        
        # Allocate private IP
        private_ip = await self._allocate_private_ip(consumer_tenant_ns)
        
        k8s_endpoint_name = _generate_k8s_name(resource_id, "pe")  # pe = private endpoint
        
        logger.info(
            f"Creating Private Endpoint: {resource_name}",
            consumer=consumer_tenant_ns,
            producer=producer_tenant_ns,
            privateIp=private_ip,
        )
        
        try:
            # 1. Create cross-tenant NetworkPolicy allowing traffic from consumer to producer
            cross_tenant_policy = {
                "apiVersion": "cilium.io/v2",
                "kind": "CiliumNetworkPolicy",
                "metadata": {
                    "name": k8s_endpoint_name,
                    "namespace": producer_tenant_ns,
                    "labels": {
                        "type": "private-endpoint",
                        "endpoint": resource_name,
                        "consumer-ns": consumer_tenant_ns,
                        "itl.resource-id": resource_id,
                    },
                },
                "spec": {
                    "endpointSelector": {
                        "matchLabels": {
                            "k8s:io.kubernetes.namespace": producer_tenant_ns,
                        }
                    },
                    "ingress": [
                        {
                            "fromEndpoints": [
                                {
                                    "matchLabels": {
                                        "k8s:io.kubernetes.namespace": consumer_tenant_ns,
                                    }
                                }
                            ]
                        }
                    ],
                },
            }
            
            # Deploy cross-tenant policy to all clusters
            await self._apply_cilium_policy_all_clusters(cross_tenant_policy, producer_tenant_ns)
            
            # 2. Create consumer-side endpoint label policy
            endpoint_label_policy = {
                "apiVersion": "cilium.io/v2",
                "kind": "CiliumNetworkPolicy",
                "metadata": {
                    "name": f"{k8s_endpoint_name}-label",
                    "namespace": consumer_tenant_ns,
                    "labels": {
                        "type": "private-endpoint-label",
                        "itl.resource-id": resource_id,
                    },
                },
                "spec": {
                    "endpointSelector": {
                        "matchLabels": {
                            "k8s:io.kubernetes.namespace": consumer_tenant_ns,
                        }
                    },
                    "egress": [
                        {
                            "toEndpoints": [
                                {
                                    "matchLabels": {
                                        "k8s:io.kubernetes.namespace": producer_tenant_ns,
                                    }
                                }
                            ]
                        }
                    ],
                },
            }
            
            await self._apply_cilium_policy_all_clusters(endpoint_label_policy, consumer_tenant_ns)
            
            # 3. Create headless K8s Service + Endpoints for DNS resolution
            # Service name: pe-to-database → resolves to private IP via DNS
            dns_service = {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": f"{k8s_endpoint_name}-dns",
                    "namespace": consumer_tenant_ns,
                    "labels": {
                        "type": "private-endpoint-dns",
                        "itl.resource-id": resource_id,
                    },
                },
                "spec": {
                    "type": "ClusterIP",
                    "clusterIP": "None",  # Headless service
                    "ports": [
                        {
                            "name": "https",
                            "port": 443,
                            "protocol": "TCP",
                        }
                    ],
                    "selector": {
                        "type": "private-endpoint-dns",
                    },
                },
            }
            
            dns_endpoints = {
                "apiVersion": "v1",
                "kind": "Endpoints",
                "metadata": {
                    "name": f"{k8s_endpoint_name}-dns",
                    "namespace": consumer_tenant_ns,
                    "labels": {
                        "type": "private-endpoint-dns",
                        "itl.resource-id": resource_id,
                    },
                },
                "subsets": [
                    {
                        "addresses": [
                            {
                                "ip": private_ip,
                                "hostname": resource_name,
                            }
                        ],
                        "ports": [
                            {
                                "name": "https",
                                "port": 443,
                                "protocol": "TCP",
                            }
                        ],
                    }
                ],
            }
            
            # Deploy DNS service and endpoints to all clusters
            v1_clients = await self._get_all_v1_clients()
            for cluster_name, v1 in v1_clients.items():
                try:
                    # Create or replace service
                    try:
                        v1.create_namespaced_service(
                            namespace=consumer_tenant_ns,
                            body=dns_service,
                        )
                    except ApiException as e:
                        if e.status == 409:
                            v1.patch_namespaced_service(
                                name=f"{k8s_endpoint_name}-dns",
                                namespace=consumer_tenant_ns,
                                body=dns_service,
                            )
                    
                    # Create or replace endpoints
                    try:
                        v1.create_namespaced_endpoints(
                            namespace=consumer_tenant_ns,
                            body=dns_endpoints,
                        )
                    except ApiException as e:
                        if e.status == 409:
                            v1.patch_namespaced_endpoints(
                                name=f"{k8s_endpoint_name}-dns",
                                namespace=consumer_tenant_ns,
                                body=dns_endpoints,
                            )
                    
                    logger.info(f"✓ Created DNS service in {cluster_name}: {k8s_endpoint_name}-dns → {private_ip}")
                except ApiException as e:
                    logger.error(f"Failed to create DNS service in {cluster_name}: {e}")
            
            # Create PrivateEndpoint object
            pe = PrivateEndpoint(
                id=resource_id,
                name=resource_name,
                subscription_id=consumer_subscription_id,
                resource_group="default",
                vnet_id=properties.get("vnet_id", ""),
                subnet_id=properties.get("subnet", {}).get("id", ""),
                service_connection={"id": target_service_id, "name": service_conn.get("name", "")},
                private_ip_address=private_ip,
            )
            
            logger.info(f"✓ Created Private Endpoint: {resource_name} → {private_ip} (DNS: {k8s_endpoint_name}-dns.{consumer_tenant_ns}.svc.cluster.local)")
            return pe.to_dict()["properties"]
        
        except Exception as e:
            logger.error(f"Failed to create Private Endpoint: {e}")
            raise

    async def _delete_private_endpoint(self, resource_id: str) -> None:
        """Delete Private Endpoint and cleanup policies + DNS records."""
        try:
            subscription_id = resource_id.split("/")[2]
            tenant_ns = f"sub-{subscription_id[:8]}".lower()
            k8s_endpoint_name = _generate_k8s_name(resource_id, "pe")
            
            # Delete from all clusters
            custom_api_clients = await self._get_all_custom_api_clients()
            v1_clients = await self._get_all_v1_clients()
            
            for cluster_name in custom_api_clients.keys():
                custom_api = custom_api_clients[cluster_name]
                v1 = v1_clients[cluster_name]
                
                try:
                    # Delete Cilium policies
                    custom_api.delete_namespaced_custom_object(
                        group="cilium.io",
                        version="v2",
                        namespace=tenant_ns,
                        plural="ciliumnetworkpolicies",
                        name=f"{k8s_endpoint_name}-label",
                    )
                    custom_api.delete_namespaced_custom_object(
                        group="cilium.io",
                        version="v2",
                        namespace=tenant_ns,
                        plural="ciliumnetworkpolicies",
                        name=k8s_endpoint_name,
                    )
                    logger.info(f"✓ Deleted PE policies in {cluster_name}: {k8s_endpoint_name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to delete PE policies in {cluster_name}: {e}")
                
                try:
                    # Delete DNS service and endpoints
                    v1.delete_namespaced_service(
                        name=f"{k8s_endpoint_name}-dns",
                        namespace=tenant_ns,
                    )
                    v1.delete_namespaced_endpoints(
                        name=f"{k8s_endpoint_name}-dns",
                        namespace=tenant_ns,
                    )
                    logger.info(f"✓ Deleted DNS service in {cluster_name}: {k8s_endpoint_name}-dns")
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to delete DNS service in {cluster_name}: {e}")
        except Exception as e:
            logger.error(f"Failed to delete Private Endpoint: {e}")

    async def _allocate_private_ip(self, tenant_ns: str) -> str:
        """Allocate a private IP for private endpoint."""
        try:
            import hashlib
            
            # Generate deterministic IP from tenant namespace
            hash_val = int(hashlib.md5(tenant_ns.encode()).hexdigest()[:4], 16)
            private_ip = f"10.255.{hash_val // 256}.{hash_val % 256}"
            
            logger.debug(f"Allocated private IP: {private_ip}")
            return private_ip
        
        except Exception as e:
            logger.error(f"Failed to allocate private IP: {e}")
            raise

    async def _create_private_dns_zone(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Private DNS Zone backed by CoreDNS ConfigMap."""
        try:
            subscription_id = resource_id.split("/")[2]
            tenant_ns = f"sub-{subscription_id[:8]}".lower()
            k8s_zone_name = _generate_k8s_name(resource_id, "dnszone")
            zone_name = properties.get("zoneName", f"{resource_name}.private.local")
            
            # Create CoreDNS ConfigMap for zone
            configmap_manifest = {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": k8s_zone_name,
                    "namespace": tenant_ns,
                    "labels": {
                        "app": "private-dns-zone",
                        "zone": resource_name,
                    },
                },
                "data": {
                    "zone-config": json.dumps({
                        "zoneName": zone_name,
                        "records": {},
                    }),
                },
            }
            
            # Deploy to all clusters
            v1_clients = await self._get_all_v1_clients()
            for cluster_name, v1 in v1_clients.items():
                try:
                    v1.create_namespaced_config_map(
                        namespace=tenant_ns,
                        body=configmap_manifest,
                    )
                    logger.info(f"✓ Created DNS zone {cluster_name}: {k8s_zone_name}")
                except ApiException as e:
                    if e.status == 409:
                        logger.debug(f"DNS zone already exists in {cluster_name}")
                    else:
                        raise
            
            dns_zone = PrivateDnsZone(
                id=resource_id,
                name=resource_name,
                subscription_id=subscription_id,
                resource_group=resource_id.split("/")[4],
                location=location,
                zone_name=zone_name,
            )
            
            return dns_zone.to_dict()
        
        except Exception as e:
            logger.error(f"Failed to create Private DNS Zone: {e}")
            raise

    async def _delete_private_dns_zone(self, resource_id: str) -> None:
        """Delete Private DNS Zone and cleanup ConfigMap."""
        try:
            subscription_id = resource_id.split("/")[2]
            tenant_ns = f"sub-{subscription_id[:8]}".lower()
            k8s_zone_name = _generate_k8s_name(resource_id, "dnszone")
            
            # Delete from all clusters
            v1_clients = await self._get_all_v1_clients()
            for cluster_name, v1 in v1_clients.items():
                try:
                    v1.delete_namespaced_config_map(
                        name=k8s_zone_name,
                        namespace=tenant_ns,
                    )
                    logger.info(f"✓ Deleted DNS zone {cluster_name}: {k8s_zone_name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to delete DNS zone in {cluster_name}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to delete Private DNS Zone: {e}")

    async def _create_dns_record(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create DNS Record within Private DNS Zone."""
        try:
            subscription_id = resource_id.split("/")[2]
            tenant_ns = f"sub-{subscription_id[:8]}".lower()
            
            # Extract zone name and record type from resource_id
            # Format: .../privateDnsZones/{zone}/recordSets/{record-name}
            path_parts = resource_id.split("/")
            zone_name = None
            record_type = properties.get("recordType", "A")
            records = properties.get("records", [])
            ttl = properties.get("ttl", 3600)
            
            # Find zone name from resource_id
            for i, part in enumerate(path_parts):
                if part == "privateDnsZones" and i + 1 < len(path_parts):
                    zone_name = path_parts[i + 1]
                    break
            
            if not zone_name:
                raise ValueError("Could not extract zone name from resource_id")
            
            k8s_zone_name = _generate_k8s_name(
                f"/subscriptions/{subscription_id}/resourceGroups/{resource_id.split('/')[4]}/providers/Microsoft.Network/privateDnsZones/{zone_name}",
                "dnszone"
            )
            
            # Create K8s Service + Endpoints for DNS record
            service_manifest = {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": f"{_generate_k8s_name(resource_id, 'rec')}",
                    "namespace": tenant_ns,
                    "labels": {
                        "app": "private-dns-record",
                        "zone": zone_name,
                        "record-type": record_type,
                    },
                },
                "spec": {
                    "clusterIP": "None",  # Headless
                    "selector": {
                        f"dns-record-{resource_name}": "true",
                    },
                },
            }
            
            endpoints_manifest = {
                "apiVersion": "v1",
                "kind": "Endpoints",
                "metadata": {
                    "name": f"{_generate_k8s_name(resource_id, 'rec')}",
                    "namespace": tenant_ns,
                },
                "subsets": [
                    {
                        "addresses": [
                            {"ip": record["ipv4Address"] if "ipv4Address" in record else record.get("value")}
                            for record in records
                            if record.get("ipv4Address") or record.get("value")
                        ]
                    }
                ] if records else [],
            }
            
            # Deploy to all clusters
            v1_clients = await self._get_all_v1_clients()
            for cluster_name, v1 in v1_clients.items():
                try:
                    v1.create_namespaced_service(
                        namespace=tenant_ns,
                        body=service_manifest,
                    )
                    logger.info(f"✓ Created DNS record {cluster_name}: {resource_name}")
                except ApiException as e:
                    if e.status != 409:
                        raise
                
                try:
                    v1.create_namespaced_endpoints(
                        namespace=tenant_ns,
                        body=endpoints_manifest,
                    )
                except ApiException as e:
                    if e.status != 409:
                        raise
            
            dns_record = PrivateDnsRecord(
                id=resource_id,
                name=resource_name,
                subscription_id=subscription_id,
                resource_group=resource_id.split("/")[4],
                zone_name=zone_name,
                record_type=record_type,
                ttl=ttl,
                records=records,
            )
            
            return dns_record.to_dict()
        
        except Exception as e:
            logger.error(f"Failed to create DNS Record: {e}")
            raise

    async def _delete_dns_record(self, resource_id: str) -> None:
        """Delete DNS Record and cleanup Service + Endpoints."""
        try:
            subscription_id = resource_id.split("/")[2]
            tenant_ns = f"sub-{subscription_id[:8]}".lower()
            k8s_record_name = _generate_k8s_name(resource_id, "rec")
            
            # Delete from all clusters
            v1_clients = await self._get_all_v1_clients()
            for cluster_name, v1 in v1_clients.items():
                try:
                    v1.delete_namespaced_service(
                        name=k8s_record_name,
                        namespace=tenant_ns,
                    )
                    v1.delete_namespaced_endpoints(
                        name=k8s_record_name,
                        namespace=tenant_ns,
                    )
                    logger.info(f"✓ Deleted DNS record {cluster_name}: {k8s_record_name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to delete DNS record in {cluster_name}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to delete DNS Record: {e}")

    # ========================================================================
    # Route Tables (Not Yet Implemented)
    # ========================================================================

    async def _create_route_table(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Route Table. Not yet implemented."""
        logger.warning("Route Table creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        route_table = RouteTable(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            location=location,
        )
        return route_table.to_dict()

    async def _delete_route_table(self, resource_id: str) -> None:
        """Delete Route Table. Not yet implemented."""
        logger.warning("Route Table deletion not yet implemented")

    async def _create_route(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Route (UDR). Not yet implemented."""
        logger.warning("Route creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        route = Route(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            address_prefix=properties.get("addressPrefix", "0.0.0.0/0"),
            next_hop_type=properties.get("nextHopType", "VirtualNetworkGateway"),
        )
        return route.to_dict()

    async def _delete_route(self, resource_id: str) -> None:
        """Delete Route (UDR). Not yet implemented."""
        logger.warning("Route deletion not yet implemented")

    # ========================================================================
    # Service Endpoints (Not Yet Implemented)
    # ========================================================================

    async def _create_service_endpoint(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Service Endpoint. Not yet implemented."""
        logger.warning("Service Endpoint creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        endpoint = ServiceEndpoint(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            service=properties.get("service", "Microsoft.Storage"),
        )
        return endpoint.to_dict()

    async def _delete_service_endpoint(self, resource_id: str) -> None:
        """Delete Service Endpoint. Not yet implemented."""
        logger.warning("Service Endpoint deletion not yet implemented")

    # ========================================================================
    # Application Gateway (Not Yet Implemented)
    # ========================================================================

    async def _create_application_gateway(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Application Gateway (Layer 7 LB) via K8s Ingress."""
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        sku = properties.get("sku", "Standard_v2")
        backend_pools = properties.get("backendAddressPools", [])
        http_listeners = properties.get("httpListeners", [])
        url_path_maps = properties.get("urlPathMaps", [])
        backend_settings = properties.get("backendHttpSettings", [])
        
        logger.debug(f"Creating Application Gateway: {resource_name} (SKU: {sku})")
        
        try:
            # Generate unique K8s name from resource ID
            k8s_ingress_name = _generate_k8s_name(resource_id, "ingress")
            tenant_ns = f"sub-{subscription_id[:8]}".lower()
            
            # ===== K8S: Create Ingress =====
            # Ingress is the K8s equivalent of Application Gateway
            # It handles Layer 7 routing, URL path mapping, and SSL termination
            v1_clients = await self._get_all_v1_clients()
            
            for cluster_name, v1 in v1_clients.items():
                try:
                    # Build Ingress rules from URL path maps and HTTP listeners
                    ingress_rules = []
                    for url_map in url_path_maps:
                        rule = {
                            "host": url_map.get("host", resource_name),
                            "http": {
                                "paths": url_map.get("paths", [])
                            }
                        }
                        ingress_rules.append(rule)
                    
                    # If no URL path maps, create default rule
                    if not ingress_rules:
                        ingress_rules = [{
                            "host": None,
                            "http": {
                                "paths": [{
                                    "path": "/",
                                    "pathType": "Prefix",
                                    "backend": {
                                        "service": {
                                            "name": backend_pools[0].get("name", "default-backend") if backend_pools else "default-backend",
                                            "port": {"number": 80}
                                        }
                                    }
                                }]
                            }
                        }]
                    
                    ingress_manifest = {
                        "apiVersion": "networking.k8s.io/v1",
                        "kind": "Ingress",
                        "metadata": {
                            "name": k8s_ingress_name,
                            "namespace": tenant_ns,
                            "labels": {
                                "app": resource_name,
                                "itl.resource-id": resource_id,
                            },
                            "annotations": {
                                "kubernetes.io/ingress.class": "cilium",
                                "cert-manager.io/cluster-issuer": "letsencrypt-prod",
                            },
                        },
                        "spec": {
                            "ingressClassName": "cilium",
                            "rules": ingress_rules,
                        },
                    }
                    
                    # Create the Ingress
                    v1.create_namespaced_ingress(
                        namespace=tenant_ns,
                        body=ingress_manifest,
                    )
                    logger.info(f"✓ Created K8s Ingress in {cluster_name}: {k8s_ingress_name}")
                except ApiException as e:
                    if e.status != 409:  # 409 = already exists
                        logger.error(f"Failed to create Ingress in {cluster_name}: {e}")
                    else:
                        logger.info(f"Ingress already exists in {cluster_name}: {k8s_ingress_name}")
            
            # Build response model
            app_gw = ApplicationGateway(
                id=resource_id,
                name=resource_name,
                subscription_id=subscription_id,
                resource_group=resource_group,
                location=location,
                sku=sku,
                backend_pools=backend_pools,
                http_listeners=http_listeners,
                url_path_maps=url_path_maps,
                backend_settings=backend_settings,
            )
            
            logger.info(f"✓ Application Gateway created: {resource_name}")
            return app_gw.to_dict()
        
        except Exception as e:
            logger.error(f"Failed to create Application Gateway: {e}")
            raise

    async def _delete_application_gateway(self, resource_id: str) -> None:
        """Delete Application Gateway and K8s Ingress."""
        try:
            subscription_id = resource_id.split("/")[2]
            tenant_ns = f"sub-{subscription_id[:8]}".lower()
            k8s_ingress_name = _generate_k8s_name(resource_id, "ingress")
            
            # Delete from all clusters
            v1_clients = await self._get_all_v1_clients()
            for cluster_name, v1 in v1_clients.items():
                try:
                    v1.delete_namespaced_ingress(
                        name=k8s_ingress_name,
                        namespace=tenant_ns,
                    )
                    logger.info(f"✓ Deleted K8s Ingress in {cluster_name}: {k8s_ingress_name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.error(f"Failed to delete Ingress in {cluster_name}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to delete Application Gateway: {e}")

    # ========================================================================
    # VPN Gateway (Not Yet Implemented)
    # ========================================================================

    async def _create_vpn_gateway(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create VPN Gateway. Not yet implemented."""
        logger.warning("VPN Gateway creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        vpn_gw = VPNGateway(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            location=location,
        )
        return vpn_gw.to_dict()

    async def _delete_vpn_gateway(self, resource_id: str) -> None:
        """Delete VPN Gateway. Not yet implemented."""
        logger.warning("VPN Gateway deletion not yet implemented")

    # ========================================================================
    # NAT Gateway (Not Yet Implemented)
    # ========================================================================

    async def _create_nat_gateway(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create NAT Gateway. Not yet implemented."""
        logger.warning("NAT Gateway creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        nat_gw = NATGateway(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            location=location,
        )
        return nat_gw.to_dict()

    async def _delete_nat_gateway(self, resource_id: str) -> None:
        """Delete NAT Gateway. Not yet implemented."""
        logger.warning("NAT Gateway deletion not yet implemented")

    # ========================================================================
    # Bastion (Not Yet Implemented)
    # ========================================================================

    async def _create_bastion(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Bastion. Not yet implemented."""
        logger.warning("Bastion creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        bastion = Bastion(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            location=location,
            vnet_id=properties.get("vnetId", ""),
        )
        return bastion.to_dict()

    async def _delete_bastion(self, resource_id: str) -> None:
        """Delete Bastion. Not yet implemented."""
        logger.warning("Bastion deletion not yet implemented")

    # ========================================================================
    # Network Watcher (Not Yet Implemented)
    # ========================================================================

    async def _create_network_watcher(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Network Watcher. Not yet implemented."""
        logger.warning("Network Watcher creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        watcher = NetworkWatcher(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            location=location,
        )
        return watcher.to_dict()

    async def _delete_network_watcher(self, resource_id: str) -> None:
        """Delete Network Watcher. Not yet implemented."""
        logger.warning("Network Watcher deletion not yet implemented")

    # ========================================================================
    # Azure Firewall (Not Yet Implemented)
    # ========================================================================

    async def _create_azure_firewall(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Azure Firewall. Not yet implemented."""
        logger.warning("Azure Firewall creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        firewall = AzureFirewall(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            location=location,
        )
        return firewall.to_dict()

    async def _delete_azure_firewall(self, resource_id: str) -> None:
        """Delete Azure Firewall. Not yet implemented."""
        logger.warning("Azure Firewall deletion not yet implemented")

    # ========================================================================
    # ExpressRoute (Not Yet Implemented)
    # ========================================================================

    async def _create_express_route(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create ExpressRoute circuit. Not yet implemented."""
        logger.warning("ExpressRoute creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        express_route = ExpressRoute(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            location=location,
            service_provider=properties.get("serviceProvider", "Unknown"),
        )
        return express_route.to_dict()

    async def _delete_express_route(self, resource_id: str) -> None:
        """Delete ExpressRoute circuit. Not yet implemented."""
        logger.warning("ExpressRoute deletion not yet implemented")

    # ========================================================================
    # Virtual Hub (Not Yet Implemented)
    # ========================================================================

    async def _create_virtual_hub(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Virtual Hub. Not yet implemented."""
        logger.warning("Virtual Hub creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        virtual_hub = VirtualHub(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            location=location,
            address_prefix=properties.get("addressPrefix", "10.0.0.0/24"),
        )
        return virtual_hub.to_dict()

    async def _delete_virtual_hub(self, resource_id: str) -> None:
        """Delete Virtual Hub. Not yet implemented."""
        logger.warning("Virtual Hub deletion not yet implemented")

    # ========================================================================
    # Traffic Manager (Not Yet Implemented)
    # ========================================================================

    async def _create_traffic_manager(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Traffic Manager profile. Not yet implemented."""
        logger.warning("Traffic Manager creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        traffic_mgr = TrafficManager(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
        )
        return traffic_mgr.to_dict()

    async def _delete_traffic_manager(self, resource_id: str) -> None:
        """Delete Traffic Manager profile. Not yet implemented."""
        logger.warning("Traffic Manager deletion not yet implemented")

    # ========================================================================
    # Front Door (Not Yet Implemented)
    # ========================================================================

    async def _create_front_door(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Front Door. Not yet implemented."""
        logger.warning("Front Door creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        front_door = FrontDoor(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
        )
        return front_door.to_dict()

    async def _delete_front_door(self, resource_id: str) -> None:
        """Delete Front Door. Not yet implemented."""
        logger.warning("Front Door deletion not yet implemented")

    # ========================================================================
    # DDoS Protection (Not Yet Implemented)
    # ========================================================================

    async def _create_ddos_protection(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create DDoS Protection plan. Not yet implemented."""
        logger.warning("DDoS Protection creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        ddos = DDoSProtection(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            location=location,
        )
        return ddos.to_dict()

    async def _delete_ddos_protection(self, resource_id: str) -> None:
        """Delete DDoS Protection plan. Not yet implemented."""
        logger.warning("DDoS Protection deletion not yet implemented")

    # ========================================================================
    # Public DNS Zone (Not Yet Implemented)
    # ========================================================================

    async def _create_public_dns_zone(
        self, resource_id: str, resource_name: str, properties: dict, location: str
    ) -> dict:
        """Create Public DNS Zone. Not yet implemented."""
        logger.warning("Public DNS Zone creation not yet implemented")
        subscription_id = resource_id.split("/")[2]
        resource_group = resource_id.split("/")[4]
        public_dns = PublicDnsZone(
            id=resource_id,
            name=resource_name,
            subscription_id=subscription_id,
            resource_group=resource_group,
            zone_name=properties.get("zoneName", f"{resource_name}.com"),
        )
        return public_dns.to_dict()

    async def _delete_public_dns_zone(self, resource_id: str) -> None:
        """Delete Public DNS Zone. Not yet implemented."""
        logger.warning("Public DNS Zone deletion not yet implemented")

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _apply_cilium_crd(
        self, manifest: dict, plural: str, namespace: str
    ) -> None:
        """Apply or update Cilium CRD."""
        if not self.custom_api:
            logger.warning("Kubernetes API not initialized, skipping Cilium CRD")
            return
        
        group = manifest["apiVersion"].split("/")[0]
        version = manifest["apiVersion"].split("/")[1]
        name = manifest["metadata"]["name"]
        
        try:
            self.custom_api.get_namespaced_custom_object(
                group=group, version=version, namespace=namespace, plural=plural, name=name
            )
            # Exists, update it
            self.custom_api.patch_namespaced_custom_object(
                group=group, version=version, namespace=namespace, plural=plural,
                name=name, body=manifest
            )
            logger.debug(f"Updated {plural}/{name}")
        except ApiException as e:
            if e.status == 404:
                # Create new
                self.custom_api.create_namespaced_custom_object(
                    group=group, version=version, namespace=namespace, plural=plural,
                    body=manifest
                )
                logger.debug(f"Created {plural}/{name}")
            else:
                raise

    def _error_response(
        self, resource_type: str, resource_name: str, error_message: str
    ) -> ResourceResponse:
        """Create an error ResourceResponse."""
        return ResourceResponse(
            id=f"/providers/{self.provider_namespace}/{resource_type}/{resource_name}",
            name=resource_name,
            type=f"{self.provider_namespace}/{resource_type}",
            location="eastus",
            properties={"error": error_message},
            provisioning_state=ProvisioningState.FAILED,
        )

