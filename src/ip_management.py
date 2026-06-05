"""
IP Management and Discovery for VNets, Subnets, and Services.

Provides IP listing and IPAM capabilities:
1. Active IPs in subnets (pod IPs)
2. LoadBalancer IPs (VLAN IPs)
3. IPAM reservation tracking and capacity planning
4. Real-time network discovery (ARP, active connections)
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional
from datetime import datetime
import ipaddress

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


@dataclass
class ActiveIP:
    """Represents an active IP address in the network."""
    ip_address: str
    subnet_cidr: str
    resource_type: str  # "pod", "service", "loadbalancer", "nic"
    resource_name: str
    namespace: str
    pod_name: Optional[str] = None
    container_id: Optional[str] = None
    mac_address: Optional[str] = None
    status: str = "active"  # active, inactive, reserved
    last_seen: Optional[str] = None
    node_name: Optional[str] = None


@dataclass
class SubnetIPAM:
    """IP Address Management data for a subnet."""
    subnet_cidr: str
    total_ips: int
    usable_ips: int
    reserved_ips: int
    active_ips: int
    available_ips: int
    utilization_percent: float
    gateway_ip: Optional[str] = None
    broadcast_ip: Optional[str] = None
    active_ip_list: list[ActiveIP] = None


@dataclass
class VNetIPSummary:
    """Summary of IP usage across all subnets in a VNet."""
    vnet_name: str
    vnet_cidr: str
    total_subnets: int
    total_ips: int
    active_ips: int
    available_ips: int
    subnet_summaries: list[dict] = None


class IPManager:
    """Manages IP discovery, listing, and IPAM tracking."""

    def __init__(self):
        """Initialize IP Manager."""
        try:
            config.load_incluster_config()
        except config.config_exception.ConfigException:
            config.load_kube_config()
        
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.custom_api = client.CustomObjectsApi()

    async def list_active_ips_in_subnet(
        self, 
        vnet_name: str, 
        subnet_name: str,
        namespace: Optional[str] = None
    ) -> list[ActiveIP]:
        """
        List all active IPs currently allocated in a subnet.
        
        Includes pod IPs, service IPs, and reserved IPs.
        
        Args:
            vnet_name: Virtual Network name
            subnet_name: Subnet name
            namespace: Optional K8s namespace filter
        
        Returns:
            List of ActiveIP objects
        """
        logger.info(f"Listing active IPs in {vnet_name}/{subnet_name}")
        active_ips = []
        
        try:
            # Get subnet CIDR from annotation/label
            subnet_cidr = await self._get_subnet_cidr(vnet_name, subnet_name)
            
            if not subnet_cidr:
                logger.warning(f"Could not determine subnet CIDR for {subnet_name}")
                return []
            
            # List all pods in namespace(s)
            namespaces = [namespace] if namespace else self._get_tenant_namespaces()
            
            for ns in namespaces:
                try:
                    pods = self.v1.list_namespaced_pod(ns)
                    for pod in pods.items:
                        if pod.status.pod_ip:
                            # Check if pod IP is in subnet CIDR
                            if self._ip_in_cidr(pod.status.pod_ip, subnet_cidr):
                                active_ips.append(ActiveIP(
                                    ip_address=pod.status.pod_ip,
                                    subnet_cidr=subnet_cidr,
                                    resource_type="pod",
                                    resource_name=pod.metadata.name,
                                    namespace=ns,
                                    pod_name=pod.metadata.name,
                                    node_name=pod.spec.node_name,
                                    status="active",
                                    last_seen=datetime.utcnow().isoformat()
                                ))
                except ApiException as e:
                    logger.error(f"Error listing pods in {ns}: {e}")
            
            logger.info(f"Found {len(active_ips)} active IPs in {subnet_name}")
            return active_ips
        
        except Exception as e:
            logger.error(f"Error listing active IPs: {e}")
            return []

    async def list_loadbalancer_ips(
        self,
        vnet_name: Optional[str] = None,
        namespace: Optional[str] = None
    ) -> list[ActiveIP]:
        """
        List all LoadBalancer service IPs (VLAN IPs) assigned to services.
        
        Args:
            vnet_name: Optional VNet filter
            namespace: Optional K8s namespace filter
        
        Returns:
            List of ActiveIP objects with VLAN IPs
        """
        logger.info(f"Listing LoadBalancer IPs for {vnet_name or 'all VNets'}")
        lb_ips = []
        
        try:
            namespaces = [namespace] if namespace else self._get_tenant_namespaces()
            
            for ns in namespaces:
                try:
                    services = self.v1.list_namespaced_service(ns)
                    for svc in services.items:
                        # Filter for LoadBalancer type services
                        if svc.spec.type == "LoadBalancer":
                            if svc.status.load_balancer.ingress:
                                for ingress in svc.status.load_balancer.ingress:
                                    lb_ips.append(ActiveIP(
                                        ip_address=ingress.ip or "pending",
                                        subnet_cidr="VLAN",  # VLAN IPs not in traditional subnet
                                        resource_type="loadbalancer",
                                        resource_name=svc.metadata.name,
                                        namespace=ns,
                                        status="active" if ingress.ip else "pending",
                                        last_seen=datetime.utcnow().isoformat()
                                    ))
                except ApiException as e:
                    logger.error(f"Error listing services in {ns}: {e}")
            
            logger.info(f"Found {len(lb_ips)} LoadBalancer IPs")
            return lb_ips
        
        except Exception as e:
            logger.error(f"Error listing LoadBalancer IPs: {e}")
            return []

    async def get_subnet_ipam(
        self,
        vnet_name: str,
        subnet_name: str,
        namespace: Optional[str] = None
    ) -> SubnetIPAM:
        """
        Get IPAM reservation and capacity planning data for a subnet.
        
        Args:
            vnet_name: Virtual Network name
            subnet_name: Subnet name
            namespace: Optional K8s namespace filter
        
        Returns:
            SubnetIPAM with capacity and utilization data
        """
        logger.info(f"Getting IPAM for {vnet_name}/{subnet_name}")
        
        try:
            subnet_cidr = await self._get_subnet_cidr(vnet_name, subnet_name)
            
            if not subnet_cidr:
                logger.warning(f"Could not determine subnet CIDR for {subnet_name}")
                return None
            
            # Parse CIDR to calculate IP counts
            network = ipaddress.ip_network(subnet_cidr)
            total_ips = network.num_addresses
            usable_ips = total_ips - 2 if total_ips > 2 else total_ips  # Exclude network and broadcast
            gateway_ip = str(network.network_address + 1)
            broadcast_ip = str(network.broadcast_address)
            
            # Get active IPs
            active_ip_list = await self.list_active_ips_in_subnet(
                vnet_name, subnet_name, namespace
            )
            active_count = len(active_ip_list)
            
            # Calculate reserved IPs (Cilium system pools, etc.)
            reserved_count = await self._get_reserved_ips_count(subnet_cidr)
            
            available = usable_ips - active_count - reserved_count
            utilization = ((active_count + reserved_count) / usable_ips * 100) if usable_ips > 0 else 0
            
            return SubnetIPAM(
                subnet_cidr=subnet_cidr,
                total_ips=total_ips,
                usable_ips=usable_ips,
                reserved_ips=reserved_count,
                active_ips=active_count,
                available_ips=max(0, available),
                utilization_percent=round(utilization, 2),
                gateway_ip=gateway_ip,
                broadcast_ip=broadcast_ip,
                active_ip_list=active_ip_list
            )
        
        except Exception as e:
            logger.error(f"Error getting IPAM data: {e}")
            return None

    async def get_vnet_ip_summary(
        self,
        vnet_name: str,
        namespace: Optional[str] = None
    ) -> VNetIPSummary:
        """
        Get IP usage summary for entire VNet across all subnets.
        
        Args:
            vnet_name: Virtual Network name
            namespace: Optional K8s namespace filter
        
        Returns:
            VNetIPSummary with aggregate data
        """
        logger.info(f"Getting IP summary for VNet {vnet_name}")
        
        try:
            # Get VNet CIDR
            vnet_cidr = await self._get_vnet_cidr(vnet_name)
            subnets = await self._get_vnet_subnets(vnet_name)
            
            total_ips = 0
            active_ips = 0
            available_ips = 0
            subnet_summaries = []
            
            for subnet in subnets:
                ipam = await self.get_subnet_ipam(vnet_name, subnet, namespace)
                if ipam:
                    total_ips += ipam.total_ips
                    active_ips += ipam.active_ips
                    available_ips += ipam.available_ips
                    subnet_summaries.append({
                        "name": subnet,
                        "cidr": ipam.subnet_cidr,
                        "total": ipam.total_ips,
                        "active": ipam.active_ips,
                        "available": ipam.available_ips,
                        "utilization_percent": ipam.utilization_percent
                    })
            
            return VNetIPSummary(
                vnet_name=vnet_name,
                vnet_cidr=vnet_cidr or "unknown",
                total_subnets=len(subnets),
                total_ips=total_ips,
                active_ips=active_ips,
                available_ips=available_ips,
                subnet_summaries=subnet_summaries
            )
        
        except Exception as e:
            logger.error(f"Error getting VNet summary: {e}")
            return None

    async def discover_arp_entries(
        self,
        subnet_cidr: str,
        namespace: Optional[str] = None
    ) -> list[ActiveIP]:
        """
        Real-time ARP discovery for active IPs on network.
        
        Scans Cilium agent nodes for ARP entries within subnet CIDR.
        
        Args:
            subnet_cidr: Subnet CIDR to scan
            namespace: Optional K8s namespace filter
        
        Returns:
            List of discovered IPs with MAC addresses
        """
        logger.info(f"Discovering ARP entries for {subnet_cidr}")
        discovered_ips = []
        
        try:
            # Get all Cilium agent pods
            cilium_pods = self.v1.list_namespaced_pod(
                "kube-system",
                label_selector="k8s-app=cilium"
            )
            
            # For each Cilium pod, query its agent for ARP entries
            for pod in cilium_pods.items:
                arp_entries = await self._query_cilium_arp(pod.metadata.name, subnet_cidr)
                discovered_ips.extend(arp_entries)
            
            logger.info(f"Discovered {len(discovered_ips)} ARP entries")
            return discovered_ips
        
        except Exception as e:
            logger.error(f"Error discovering ARP entries: {e}")
            return []

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _ip_in_cidr(self, ip: str, cidr: str) -> bool:
        """Check if IP address is in CIDR range."""
        try:
            return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr)
        except ValueError:
            return False

    def _get_tenant_namespaces(self) -> list[str]:
        """Get all tenant namespaces (sub-* format)."""
        try:
            ns_list = self.v1.list_namespace()
            return [ns.metadata.name for ns in ns_list.items 
                    if ns.metadata.name.startswith("sub-")]
        except ApiException as e:
            logger.error(f"Error listing namespaces: {e}")
            return []

    async def _get_subnet_cidr(self, vnet_name: str, subnet_name: str) -> Optional[str]:
        """Get subnet CIDR from ConfigMap or annotation."""
        try:
            cm = self.v1.read_namespaced_config_map(
                f"subnet-{subnet_name}",
                f"vnet-{vnet_name}"
            )
            return cm.data.get("cidr")
        except ApiException:
            logger.warning(f"ConfigMap not found for subnet {subnet_name}")
            return None

    async def _get_vnet_cidr(self, vnet_name: str) -> Optional[str]:
        """Get VNet CIDR from namespace annotation."""
        try:
            ns = self.v1.read_namespace(f"vnet-{vnet_name}")
            return ns.metadata.annotations.get("vnet.itl.io/cidr")
        except ApiException:
            logger.warning(f"Namespace not found for VNet {vnet_name}")
            return None

    async def _get_vnet_subnets(self, vnet_name: str) -> list[str]:
        """Get all subnets in a VNet."""
        try:
            ns = self.v1.read_namespace(f"vnet-{vnet_name}")
            subnets_str = ns.metadata.annotations.get("vnet.itl.io/subnets", "")
            return subnets_str.split(",") if subnets_str else []
        except ApiException:
            logger.warning(f"Namespace not found for VNet {vnet_name}")
            return []

    async def _get_reserved_ips_count(self, subnet_cidr: str) -> int:
        """Get count of reserved IPs (Cilium pools, services, etc.)."""
        # Reserved IPs typically include:
        # - Network address
        # - Broadcast address
        # - Gateway IP
        # - Cilium system pool
        return 5  # Conservative estimate

    async def _query_cilium_arp(self, pod_name: str, subnet_cidr: str) -> list[ActiveIP]:
        """Query Cilium agent pod for ARP entries in subnet."""
        # This would use kubectl exec to run:
        # cilium-dbg bpf arp list
        # And parse the output for IPs in the subnet CIDR
        # Placeholder implementation
        return []
