"""
ITL Network Provider - Main entry point.

Provides Azure-style networking on Kubernetes using Cilium + Talos:
- Virtual Networks (VNets) with multi-cluster support
- Subnets with IPAM
- Network Security Groups (NSGs)
- Network Interfaces (NICs)
- Load Balancers (Layer 4)
- Application Gateways (Layer 7)
- Public IP Addresses
- Private Links and Private DNS
- BGP Peering for multi-site routing

Runs on port 8002 with multi-cluster fanout to storage, data, and compute clusters.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query
from itl_controlplane_sdk.base import BaseProviderServer
from itl_controlplane_sdk.exceptions import ProviderException

from src.provider import NetworkProvider
from src.ip_management import IPManager

logger = logging.getLogger(__name__)


class NetworkProviderServer(BaseProviderServer):
    """Network Provider server implementation."""

    def __init__(self):
        """Initialize the network provider server."""
        self.provider = NetworkProvider()
        self.ip_manager = IPManager()

    async def initialize(self) -> None:
        """Initialize provider resources."""
        logger.info("Initializing Network Provider")
        await self.provider.initialize()

    async def shutdown(self) -> None:
        """Cleanup provider resources."""
        logger.info("Shutting down Network Provider")
        await self.provider.shutdown()


# Initialize provider server
_server = NetworkProviderServer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown (FastAPI 0.93+)."""
    # Startup
    logger.info("Network Provider starting up")
    await _server.initialize()
    yield
    # Shutdown
    logger.info("Network Provider shutting down")
    await _server.shutdown()


# Create FastAPI app with modern lifespan pattern
app = FastAPI(
    title="ITL Network Provider",
    description="Network provider for ITL ControlPlane (VNets, NSGs, NICs, LBs)",
    version="1.0.0",
    lifespan=lifespan,
)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "itl-network-provider"}


# ============================================================================
# IP Management & Discovery Endpoints
# ============================================================================

@app.get("/api/v1/vnets/{vnet_name}/subnets/{subnet_name}/active-ips")
async def list_active_ips(
    vnet_name: str,
    subnet_name: str,
    namespace: Optional[str] = Query(None, description="Optional K8s namespace filter")
) -> dict:
    """
    List all active IPs currently allocated in a subnet.
    
    Returns pod IPs, service IPs, and reserved IPs in the subnet.
    
    **Query Parameters:**
    - `namespace`: Optional K8s namespace to filter by
    
    **Response:**
    ```json
    {
      "subnet": "subnet-name",
      "cidr": "10.0.1.0/24",
      "active_ips": [
        {
          "ip_address": "10.0.1.5",
          "resource_type": "pod",
          "resource_name": "app-deployment-abc123",
          "namespace": "sub-00000001",
          "node_name": "node-1",
          "status": "active"
        },
        ...
      ],
      "total_count": 42
    }
    ```
    """
    try:
        active_ips = await _server.ip_manager.list_active_ips_in_subnet(
            vnet_name, subnet_name, namespace
        )
        return {
            "subnet": subnet_name,
            "vnet": vnet_name,
            "active_ips": [
                {
                    "ip_address": ip.ip_address,
                    "subnet_cidr": ip.subnet_cidr,
                    "resource_type": ip.resource_type,
                    "resource_name": ip.resource_name,
                    "namespace": ip.namespace,
                    "pod_name": ip.pod_name,
                    "node_name": ip.node_name,
                    "status": ip.status,
                    "last_seen": ip.last_seen
                }
                for ip in active_ips
            ],
            "total_count": len(active_ips)
        }
    except Exception as e:
        logger.error(f"Error listing active IPs: {e}")
        return {
            "error": str(e),
            "subnet": subnet_name,
            "vnet": vnet_name,
            "active_ips": [],
            "total_count": 0
        }


@app.get("/api/v1/vnets/{vnet_name}/loadbalancer-ips")
async def list_loadbalancer_ips(
    vnet_name: Optional[str] = None,
    namespace: Optional[str] = Query(None, description="Optional K8s namespace filter")
) -> dict:
    """
    List all LoadBalancer service IPs (VLAN IPs) assigned to services in a VNet.
    
    These are external IPs advertised via BGP to the physical network.
    
    **Query Parameters:**
    - `vnet_name`: Optional VNet filter (if not in path)
    - `namespace`: Optional K8s namespace to filter by
    
    **Response:**
    ```json
    {
      "loadbalancer_ips": [
        {
          "ip_address": "10.200.0.50",
          "resource_type": "loadbalancer",
          "resource_name": "api-lb",
          "namespace": "sub-00000001",
          "status": "active"
        },
        ...
      ],
      "total_count": 8,
      "total_pending": 2
    }
    ```
    """
    try:
        lb_ips = await _server.ip_manager.list_loadbalancer_ips(vnet_name, namespace)
        active_count = sum(1 for ip in lb_ips if ip.status == "active")
        pending_count = sum(1 for ip in lb_ips if ip.status == "pending")
        
        return {
            "vnet": vnet_name or "all",
            "loadbalancer_ips": [
                {
                    "ip_address": ip.ip_address,
                    "resource_type": ip.resource_type,
                    "resource_name": ip.resource_name,
                    "namespace": ip.namespace,
                    "status": ip.status,
                    "last_seen": ip.last_seen
                }
                for ip in lb_ips
            ],
            "total_count": len(lb_ips),
            "active_count": active_count,
            "pending_count": pending_count
        }
    except Exception as e:
        logger.error(f"Error listing LoadBalancer IPs: {e}")
        return {
            "error": str(e),
            "vnet": vnet_name or "all",
            "loadbalancer_ips": [],
            "total_count": 0
        }


@app.get("/api/v1/vnets/{vnet_name}/subnets/{subnet_name}/ipam")
async def get_subnet_ipam(
    vnet_name: str,
    subnet_name: str,
    namespace: Optional[str] = Query(None, description="Optional K8s namespace filter")
) -> dict:
    """
    Get IPAM reservation and capacity planning data for a subnet.
    
    Shows total IP count, utilized, reserved, available, and utilization percentage.
    
    **Query Parameters:**
    - `namespace`: Optional K8s namespace to filter by
    
    **Response:**
    ```json
    {
      "subnet_cidr": "10.0.1.0/24",
      "total_ips": 256,
      "usable_ips": 254,
      "active_ips": 42,
      "reserved_ips": 12,
      "available_ips": 200,
      "utilization_percent": 21.3,
      "gateway_ip": "10.0.1.1",
      "broadcast_ip": "10.0.1.255"
    }
    ```
    """
    try:
        ipam = await _server.ip_manager.get_subnet_ipam(vnet_name, subnet_name, namespace)
        
        if not ipam:
            return {
                "error": f"Could not determine IPAM for {subnet_name}",
                "subnet": subnet_name,
                "vnet": vnet_name
            }
        
        return {
            "subnet": subnet_name,
            "vnet": vnet_name,
            "subnet_cidr": ipam.subnet_cidr,
            "total_ips": ipam.total_ips,
            "usable_ips": ipam.usable_ips,
            "active_ips": ipam.active_ips,
            "reserved_ips": ipam.reserved_ips,
            "available_ips": ipam.available_ips,
            "utilization_percent": ipam.utilization_percent,
            "gateway_ip": ipam.gateway_ip,
            "broadcast_ip": ipam.broadcast_ip
        }
    except Exception as e:
        logger.error(f"Error getting IPAM data: {e}")
        return {
            "error": str(e),
            "subnet": subnet_name,
            "vnet": vnet_name
        }


@app.get("/api/v1/vnets/{vnet_name}/ip-summary")
async def get_vnet_ip_summary(
    vnet_name: str,
    namespace: Optional[str] = Query(None, description="Optional K8s namespace filter")
) -> dict:
    """
    Get IP usage summary for entire VNet across all subnets.
    
    Aggregates IPAM data from all subnets within the VNet.
    
    **Query Parameters:**
    - `namespace`: Optional K8s namespace to filter by
    
    **Response:**
    ```json
    {
      "vnet_name": "prod-vnet",
      "vnet_cidr": "10.0.0.0/16",
      "total_subnets": 3,
      "total_ips": 768,
      "active_ips": 145,
      "available_ips": 623,
      "utilization_percent": 18.8,
      "subnet_summaries": [
        {
          "name": "prod-subnet-1",
          "cidr": "10.0.1.0/24",
          "total": 256,
          "active": 42,
          "available": 200,
          "utilization_percent": 21.3
        },
        ...
      ]
    }
    ```
    """
    try:
        summary = await _server.ip_manager.get_vnet_ip_summary(vnet_name, namespace)
        
        if not summary:
            return {
                "error": f"Could not determine IP summary for {vnet_name}",
                "vnet": vnet_name
            }
        
        total_utilization = (
            (summary.active_ips / summary.total_ips * 100)
            if summary.total_ips > 0 else 0
        )
        
        return {
            "vnet_name": summary.vnet_name,
            "vnet_cidr": summary.vnet_cidr,
            "total_subnets": summary.total_subnets,
            "total_ips": summary.total_ips,
            "active_ips": summary.active_ips,
            "available_ips": summary.available_ips,
            "utilization_percent": round(total_utilization, 2),
            "subnet_summaries": summary.subnet_summaries or []
        }
    except Exception as e:
        logger.error(f"Error getting VNet summary: {e}")
        return {
            "error": str(e),
            "vnet": vnet_name
        }


@app.get("/api/v1/network/arp-discovery")
async def discover_arp_entries(
    subnet_cidr: str = Query(..., description="Subnet CIDR to scan (e.g., 10.0.0.0/24)"),
    namespace: Optional[str] = Query(None, description="Optional K8s namespace filter")
) -> dict:
    """
    Real-time ARP discovery for active IPs on network.
    
    Scans Cilium agent nodes for ARP entries within specified subnet CIDR.
    
    **Query Parameters:**
    - `subnet_cidr`: Subnet CIDR to scan (required)
    - `namespace`: Optional K8s namespace to filter by
    
    **Response:**
    ```json
    {
      "subnet_cidr": "10.0.0.0/24",
      "discovered_ips": [
        {
          "ip_address": "10.0.0.50",
          "resource_type": "arp_discovery",
          "mac_address": "52:54:00:12:34:56",
          "status": "active",
          "last_seen": "2026-06-05T12:34:56Z"
        },
        ...
      ],
      "total_discovered": 15
    }
    ```
    """
    try:
        discovered = await _server.ip_manager.discover_arp_entries(subnet_cidr, namespace)
        
        return {
            "subnet_cidr": subnet_cidr,
            "discovered_ips": [
                {
                    "ip_address": ip.ip_address,
                    "mac_address": ip.mac_address,
                    "resource_type": ip.resource_type,
                    "status": ip.status,
                    "last_seen": ip.last_seen
                }
                for ip in discovered
            ],
            "total_discovered": len(discovered)
        }
    except Exception as e:
        logger.error(f"Error discovering ARP entries: {e}")
        return {
            "error": str(e),
            "subnet_cidr": subnet_cidr,
            "discovered_ips": [],
            "total_discovered": 0
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
        log_level="info",
    )
