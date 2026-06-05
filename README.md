# ITL Network Provider

![Status](https://img.shields.io/badge/status-alpha-orange?style=flat-square)
![Development](https://img.shields.io/badge/development-in%20progress-yellow?style=flat-square)

> **Alpha** — This project is under active development. APIs, data models, and behaviour may change without notice.

Network provider for the ITL ControlPlane SDK. Provides Azure-compatible networking abstractions (VNets, Subnets, NSGs, Load Balancers, Application Gateways, Private Links, Private DNS) deployed on Kubernetes with Cilium SDN. Supports multi-cluster topology with tenant isolation.

## Features

- [x] **Virtual Networks**: Create and manage isolated VNets per subscription
- [x] **Subnets**: IPAM with configurable address prefixes
- [x] **Security Groups**: NSGs with L3/L4 Cilium policies
- [x] **Network Interfaces**: Pod/VM network attachments
- [x] **Load Balancers**: Layer 4 load balancing via K8s Services
- [x] **Application Gateways**: Layer 7 load balancing with URL routing
- [x] **Public IPs**: External IP allocation from Cilium pools
- [x] **Private Links**: Service-level connectivity across tenants
- [x] **Private DNS Zones**: CoreDNS-backed internal DNS
- [x] **Multi-Cluster**: Simultaneous deployment to 3 K8s clusters
- [x] **Multi-Tenant**: Subscription-scoped isolation with overlapping CIDRs
- [x] **BGP Routing**: Multi-site networking via Cilium
- [x] **IP Discovery**: List active IPs, LoadBalancer IPs, IPAM capacity, ARP scanning

## Implementation Status

### [Fully Implemented] (Production-Ready)

| Resource | K8s Backend | Features |
|---|---|---|
| `virtualNetworks` | CiliumLoadBalancerIPPool | Multi-cluster, tenant-scoped IP pools |
| `virtualNetworks/subnets` | CiliumLoadBalancerIPPool | IPAM, configurable prefixes |
| `networkSecurityGroups` | CiliumNetworkPolicy | L3/L4 rules, priority-based |
| `networkInterfaces` | Pod/Deployment | Pod network attachments |
| `publicIPAddresses` | Cilium Pools | External IP allocation |
| `loadBalancers` | K8s Service | Layer 4, health probes |
| `applicationGateways` | K8s Ingress | Layer 7, URL routing, SSL/TLS |
| `bgpPeeringPolicies` | CiliumBGPPeeringPolicy | Multi-site routing |
| `virtualNetworkPeerings` | CiliumNetworkPolicy | Cross-VNet connectivity |
| `privateLinkServices` | CiliumNetworkPolicy + Service | Private service exposure |
| `privateEndpoints` | CiliumNetworkPolicy + Service | Consumer-side access |
| `privateDnsZones` | CoreDNS ConfigMap | Internal DNS zones |
| `privateDnsZones/recordSets` | K8s Service + Endpoints | DNS records (A, CNAME, MX, TXT, SRV) |

### [Stub Implementation] (Framework Ready, Not Yet Implemented)

Registered resources that return model objects but lack K8s integration:

- `routeTables`, `routes` 
- `serviceEndpoints`
- `vpnGateways`
- `natGateways`
- `bastionHosts`
- `networkWatchers`
- `azureFirewalls`
- `expressRouteCircuits`
- `virtualHubs`
- `trafficManagerProfiles`
- `frontDoors`
- `ddosProtectionPlans`
- `publicDnsZones`

## Quick Start

```bash
# 1. Install dependencies
pip install -e .[dev]

# 2. Start with docker-compose
docker-compose up -d

# 3. Verify health
curl http://localhost:8002/health
# Response: {"status": "healthy", "service": "itl-network-provider"}

# 4. Run locally (with hot reload)
uvicorn src.main:app --reload --port 8002
```

## API Examples

### Create a Virtual Network

```bash
curl -X POST http://localhost:8002/api/resource \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "subscriptionId": "sub-00000001",
    "resourceGroup": "prod-rg",
    "resourceType": "virtualNetworks",
    "resourceName": "vnet-prod",
    "location": "eastus",
    "properties": {
      "addressSpace": ["10.0.0.0/16"]
    }
  }'
```

### Create a Network Security Group

```bash
curl -X POST http://localhost:8002/api/resource \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "subscriptionId": "sub-00000001",
    "resourceGroup": "prod-rg",
    "resourceType": "networkSecurityGroups",
    "resourceName": "nsg-frontend",
    "location": "eastus",
    "properties": {
      "securityRules": [{
        "name": "allow-http",
        "properties": {
          "access": "Allow",
          "direction": "Inbound",
          "priority": 100,
          "protocol": "TCP",
          "destinationPortRange": "80",
          "sourceAddressPrefix": "*"
        }
      }]
    }
  }'
```

## Architecture

```
┌──────────────────────────────────────────┐
│  ITL Network Provider (port 8002)        │
│  FastAPI + SQLAlchemy + Kubernetes       │
└──────────────────────────────┬───────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
       ┌────────▼───────┐ ┌───▼──────┐ ┌───▼────────┐
       │ Storage Cluster│ │Data      │ │Compute     │
       │(Talos+Cilium)  │ │Cluster   │ │Cluster     │
       └────────────────┘ └──────────┘ └────────────┘
              ClusterMesh (cross-cluster routing)

Resources → K8s Manifests:
  VNet → Namespace + CiliumLoadBalancerIPPool
  NSG → CiliumNetworkPolicy
  LB → K8s Service (LoadBalancer)
  AppGW → K8s Ingress
  PrivateDNS → CoreDNS ConfigMap
```

## Development

### Testing

```bash
# Run all tests
pytest tests/ -v --cov=src

# Run specific test
pytest tests/test_provider.py::test_create_vnet -v
```

### Code Quality

```bash
# Format with Black
black src tests

# Lint with Ruff
ruff check --fix src tests

# Type check
mypy src --strict
```

### Docker Build & Deploy

```bash
# Build image
docker build -t itl-network-provider:latest .

# Run locally
docker run -p 8002:8002 \
  -e STORAGE_CLUSTER_ENDPOINT=http://storage:8001 \
  -e DATA_CLUSTER_ENDPOINT=http://data:8001 \
  -e COMPUTE_CLUSTER_ENDPOINT=http://compute:8001 \
  itl-network-provider:latest
```

## Roadmap

- [ ] Route Tables (custom routing)
- [ ] VPN Gateways (site-to-site/point-to-site)
- [ ] NAT Gateways (outbound NAT)
- [ ] Azure Firewall (stateful filtering)
- [ ] Network Watcher (flow logs, diagnostics)
- [ ] Express Route (dedicated circuits)
- [ ] Traffic Manager (global load balancing)
- [ ] DDoS Protection Plans

See [Implementation Status](#implementation-status) for current progress.

## License

Proprietary (ITL)

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — Design patterns and multi-cluster model
- [API_REFERENCE.md](docs/API_REFERENCE.md) — Complete API endpoints and schemas
- [GETTING_STARTED.md](docs/GETTING_STARTED.md) — Installation and setup guide
- [EXAMPLES.md](docs/EXAMPLES.md) — Real-world usage scenarios
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — Common issues and solutions

## Support

dev@itlusions.com
