---
layout: default
title: Documentation
---

# ITL.ControlPlane.ResourceProvider.Network — Documentation

## Overview

The ITL Network Resource Provider delivers Azure-style networking abstractions on Kubernetes with Cilium SDN, enabling:

- **Kubernetes-native** multi-tenant virtual networks
- **Multi-cluster** resilience (Storage/Data/Compute clusters)
- **Direct VLAN IP** assignment for external access
- **Namespace-based** isolation supporting overlapping CIDRs
- **Azure Portal-compatible** REST API and CLI

---

## Four Deployment Methods

Deploy network infrastructure without managing Cilium, BGP, or Kubernetes — we handle it for you.

### 1. **Web Portal** (5-minute setup)

Visual, step-by-step deployment. Perfect for learning.

- Create VNets, Subnets, NSGs
- Configure Peering and Load Balancers
- No code required
- See immediately in dashboard

→ Start: [End-User Examples](tutorials/00-USER_EXAMPLES.md#option-1-web-portal)

### 2. **CLI (itlc)** (2-minute setup)

Fast, scriptable command-line interface. Best for ops.

```bash
itlc vnet create --name prod-vnet --address-space 10.0.0.0/16
itlc subnet create --vnet prod-vnet --name frontend --prefix 10.0.1.0/24
itlc nsg create --name nsg-frontend --rules https,http
```

→ Start: [End-User Examples](tutorials/00-USER_EXAMPLES.md#option-2-cli-itlc)

### 3. **Terraform** (HCL, GitOps-ready)

Industry-standard IaC. Great for teams.

```hcl
resource "itl_vnet" "prod" {
  name           = "prod-vnet"
  address_space  = ["10.0.0.0/16"]
  subscription   = "sub-00000001"
}
```

→ Start: [End-User Examples](tutorials/00-USER_EXAMPLES.md#option-3-terraform)

### 4. **Bicep** (Azure-aligned, fastest)

Azure DSL. Perfect if you use Azure.

```bicep
resource vnet 'Microsoft.Network/virtualNetworks@2023-04-01' = {
  name: 'prod-vnet'
  location: 'westeurope'
  properties: {
    addressSpace: { addressPrefixes: ['10.0.0.0/16'] }
  }
}
```

→ Start: [End-User Examples](tutorials/00-USER_EXAMPLES.md#option-4-bicep)

### 5. **Pulumi** (Python IaC, in development 🚀)

Code-driven infrastructure. Full language power.

Coming soon via `itl-controlplane-network-pulumi` package.

→ Track: [Pulumi Implementation Guide](../PULUMI_DEVELOPMENT_GUIDE.md)

---

## Documentation

| Section | Purpose | Audience |
|---------|---------|----------|
| **[Concepts](concepts/)** | What, why, and how it works | Everyone (start here) |
| **[Guides](guides/)** | Role-based learning paths | Operators, Architects, Users |
| **[Setup](setup/)** | Installation & operations | Operators, DevOps |
| **[Tutorials](tutorials/)** | Hands-on step-by-step | Beginners & learning |
| **[Tasks](tasks/)** | Specific how-to procedures | Experienced users |
| **[Reference](reference/)** | API, CLI, lookups | Advanced users |

---

## Quick Start: Choose Your Path

### 🎓 I want to **understand the architecture**

1. [Overview](concepts/OVERVIEW.md) — 10 min
2. [Architecture](concepts/ARCHITECTURE.md) — 15 min
3. [Multi-Tenancy Model](concepts/MULTI_TENANCY.md) — 10 min

### 🚀 I want to **deploy infrastructure now**

1. [End-User Examples](tutorials/00-USER_EXAMPLES.md) — Choose your method (Portal/CLI/Terraform/Bicep)
2. [Quickstart](tutorials/01-QUICKSTART.md) — 10 min local setup
3. [Specific Task](tasks/) — Do it

### 🛠️ I want to **deploy and operate it**

1. [Installation](setup/INSTALLATION.md) — Prerequisites
2. [Production Deployment](setup/PRODUCTION_DEPLOYMENT.md) — HA setup
3. [For Operators](guides/FOR_OPERATORS.md) — Daily operations

### 👨‍💼 I'm **designing enterprise architecture**

1. [Architecture](concepts/ARCHITECTURE.md) — System design
2. [For Architects](guides/FOR_NETWORK_ARCHITECTS.md) — Patterns & design
3. [Multi-Cluster Design](concepts/MULTI_CLUSTER.md) — Resilience model

---

## Common Scenarios

### Deploy a web app with external IP

```
1. Create VNet (Portal/CLI/Terraform/Bicep)
2. Create Subnet 
3. Deploy Kubernetes workload
4. Expose as LoadBalancer service
5. ✅ Gets VLAN IP automatically (e.g., 10.200.0.50)
```

→ Full guide: [Expose Services](tasks/EXPOSE_WITH_LB.md)

### Multi-subscription peering

```
1. Create VNet in subscription A
2. Create VNet in subscription B
3. Create peering
4. ✅ Pods can communicate across subscriptions
```

→ Full guide: [Multi-Subscription Peering](tasks/SETUP_PEERING.md)

### Private Link connectivity

```
1. Create PrivateLink service in subnet A
2. Create PrivateEndpoint in subnet B
3. ✅ Private IP connectivity, no internet
```

→ Full guide: [Private Link Setup](tasks/SETUP_PRIVATE_LINK.md)

---

## For Different Roles

### 👨‍💻 Kubernetes Developers

Deploy applications and expose them via LoadBalancer services.

→ Start: [For Kubernetes Users](guides/users/KUBERNETES_USER.md)

**You care about:**
- How to expose Kubernetes services
- Multi-cluster service routing
- DNS integration
- Load balancer behavior

### 🔧 Infrastructure Engineers

Create and manage network resources via API or CLI.

→ Start: [For ITL API Users](guides/users/ITL_API_USER.md)

**You care about:**
- itlc CLI commands
- REST API patterns
- Multi-subscription workflows
- Private Link integration

### 🛠️ Platform Operators

Deploy, monitor, and troubleshoot the Network Provider.

→ Start: [For Operators](guides/FOR_OPERATORS.md)

**You care about:**
- Deployment & HA setup
- Scaling & capacity planning
- Monitoring & alerting
- Incident response

### 🏗️ Network Architects

Design multi-cluster topologies, BGP routing, and resilience.

→ Start: [For Network Architects](guides/FOR_NETWORK_ARCHITECTS.md)

**You care about:**
- Multi-tenant SaaS patterns
- BGP design & routing
- Security architecture
- Compliance & audit

---

## What Happens Behind the Scenes?

You deploy: **A simple VNet with 3 subnets**

You get automatically:
- ✅ Kubernetes namespaces for isolation (one per subscription)
- ✅ Cilium networking pools in all 3 clusters
- ✅ Cilium network policies (translated from NSGs)
- ✅ BGP route advertisements to your physical network
- ✅ Multi-cluster synchronization
- ✅ DNS resolution and service discovery
- ✅ Audit logging and compliance tracking
- ✅ HA failover across clusters

**But you don't manage any of this.** It just works. ✨

---

## Documentation Files

### Concepts (`concepts/`)
- `OVERVIEW.md` — Foundational overview & capabilities
- `ARCHITECTURE.md` — System design & data flows
- `MULTI_TENANCY.md` — Subscription isolation model
- `MULTI_CLUSTER.md` — 3-cluster architecture & failover
- `NETWORK_ISOLATION.md` — Cilium policies & security

### Guides (`guides/`)
- `FOR_OPERATORS.md` — Operational procedures
- `FOR_NETWORK_ARCHITECTS.md` — Design patterns & capacity planning
- `GETTING_STARTED.md` — 10-minute quick start
- `CONFIGURATION.md` — Environment setup
- `TROUBLESHOOTING.md` — Debugging & issue resolution
- `users/KUBERNETES_USER.md` — K8s app developers
- `users/ITL_API_USER.md` — Infrastructure engineers

### Setup (`setup/`)
- `INSTALLATION.md` — Prerequisites & initial setup
- `SECURITY.md` — OIDC, RBAC, encryption, compliance
- `PRODUCTION_DEPLOYMENT.md` — HA deployment & scaling
- `BGP_VLAN_SETUP.md` — Router configuration & peering

### Tutorials (`tutorials/`)
- `00-USER_EXAMPLES.md` — Portal, CLI, Terraform, Bicep, Pulumi
- `01-QUICKSTART.md` — Docker Compose local setup
- `02-MULTI_TIER_APP.md` — Real production topology
- `03-MULTI_SUBSCRIPTION.md` — Cross-subscription workflows
- `04-VLAN_EXPOSURE.md` — BGP and external access

### Tasks (`tasks/`)
- `CREATE_VNETS.md` — Create virtual networks
- `SETUP_PEERING.md` — Configure VNet peering
- `EXPOSE_WITH_LB.md` — LoadBalancer exposure
- `SETUP_PRIVATE_LINK.md` — Private Link setup
- `MANAGE_NSGS.md` — Network security groups
- `MONITOR_IPS.md` — IP discovery & monitoring
- `SCALE_CLUSTERS.md` — Cluster scaling
- `MONITORING.md` — Observability & alerting

### Reference (`reference/`)
- `API_REFERENCE.md` — REST API endpoints (ARM-style)
- `CLI_REFERENCE.md` — itlc commands
- `GLOSSARY.md` — Key terminology
- `TROUBLESHOOTING.md` — Common issues
- `IPAM_GUIDE.md` — IP address management

---

## Status

- **Version**: 1.0.0
- **Updated**: June 2026
- **Documentation Progress**: 65% complete (Phase 1)
- **Pulumi Support**: In development by Network Provider team (ETA ~2 weeks)

See [STATUS.md](STATUS.md) for full progress details.

---

## Next Steps

**New to Network Provider?** → Start with [Concepts: Overview](concepts/OVERVIEW.md)

**Ready to deploy?** → Choose your method in [End-User Examples](tutorials/00-USER_EXAMPLES.md)

**Need to operate?** → Go to [For Operators](guides/FOR_OPERATORS.md)

**Have a question?** → Check [Troubleshooting](reference/TROUBLESHOOTING.md)
