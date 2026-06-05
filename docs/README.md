---
layout: default
title: Documentation
---

# ITL.ControlPlane.ResourceProvider.Network  Documentation

## Overview

The ITL Network Resource Provider delivers Azure-style networking abstractions on Kubernetes with Cilium SDN, enabling:

- **Kubernetes-native** multi-tenant virtual networks
- **Multi-cluster** resilience (Storage/Data/Compute clusters)
- **Direct VLAN IP** assignment for external access
- **Namespace-based** isolation supporting overlapping CIDRs
- **Azure Portal-compatible** REST API and CLI

---

## I want to...

###  **Understand how it works**

Get the fundamentals before diving in.

- [**Overview**](concepts/OVERVIEW)  What is Network Provider and why you need it
- [**Architecture**](concepts/ARCHITECTURE)  System design, components, data flows
- [**Multi-Tenancy Model**](concepts/MULTI_TENANCY)  Subscription isolation & namespace mapping
- [**Multi-Cluster Design**](concepts/MULTI_CLUSTER)  3-cluster resilience and failover
- [**Network Isolation**](concepts/NETWORK_ISOLATION)  Cilium policies and security

###  **See examples first**

Real workflows showing how end-users deploy infrastructure.

- [**End-User Examples**](tutorials/00-USER_EXAMPLES)  Portal, CLI, Terraform, Bicep examples
  - Deploy a VNet with subnets via portal (5 min)
  - Deploy via CLI (itlc commands)
  - Deploy via Terraform (GitOps-ready)
  - Deploy via Bicep (Azure-aligned)

###  **Get started quickly**

Hands-on tutorials to learn by doing.

- [**10-Minute Quickstart**](tutorials/01-QUICKSTART)  Local setup with docker-compose
- [**Multi-Tier App**](tutorials/02-MULTI_TIER_APP)  Real-world production setup
- [**Multi-Subscription**](tutorials/03-MULTI_SUBSCRIPTION)  Cross-subscription peering
- [**VLAN Exposure**](tutorials/04-VLAN_EXPOSURE)  BGP and external access

###  **Deploy & operate**

Installation and operational procedures.

- [**Installation**](setup/INSTALLATION)  Initial setup & prerequisites
- [**Configuration**](setup/CONFIGURATION)  Environment variables & multi-cluster
- [**BGP + VLAN Setup**](setup/BGP_VLAN_SETUP)  Router configuration & peering
- [**Production Deployment**](setup/PRODUCTION_DEPLOYMENT)  High availability
- [**Security Best Practices**](setup/SECURITY)  Hardening & compliance

###  **Learn specific how-to guides**

Detailed instructions for specific tasks.

- [**Create Virtual Networks**](tasks/CREATE_VNETS)  VNets and subnets
- [**Set Up Peering**](tasks/SETUP_PEERING)  Connect subscriptions
- [**Expose Services**](tasks/EXPOSE_WITH_LB)  LoadBalancers & Application Gateways
- [**Private Link Setup**](tasks/SETUP_PRIVATE_LINK)  Cross-subscription private endpoints
- [**Network Security Groups**](tasks/MANAGE_NSGS)  Create & manage NSGs
- [**Monitor IP Allocation**](tasks/MONITOR_IPS)  IP discovery & IPAM
- [**Scale Clusters**](tasks/SCALE_CLUSTERS)  Add nodes & manage capacity

###  **Look up references**

Quick lookups and technical specifications.

- [**API Reference**](reference/API_REFERENCE)  All REST endpoints (ARM-style)
- [**CLI Reference**](reference/CLI_REFERENCE)  itlc commands & examples
- [**Glossary**](reference/GLOSSARY)  Key terms and definitions
- [**Troubleshooting**](reference/TROUBLESHOOTING)  Common issues & solutions
- [**IPAM Guide**](reference/IPAM_GUIDE)  IP address management

---

## I'm a...

###  **Kubernetes Developer**

You deploy Kubernetes workloads and expose them via LoadBalancer services.

 Start here: [**For Kubernetes Users**](guides/FOR_K8S_DEVELOPERS)

**Quick path:**
1. [Quickstart](tutorials/01-QUICKSTART)  10 minutes
2. [For K8s Users](guides/FOR_K8S_DEVELOPERS)  Your guide
3. [Expose Services](tasks/EXPOSE_WITH_LB)  Specific how-to
4. [Troubleshooting](reference/TROUBLESHOOTING)  When stuck

---

###  **ITL ControlPlane API User**

You create resources via `itlc` CLI or REST API to manage network infrastructure.

 Start here: [**For ITL API Users**](guides/FOR_ITL_API_USERS)

**Quick path:**
1. [Quickstart](tutorials/01-QUICKSTART)  10 minutes
2. [For API Users](guides/FOR_ITL_API_USERS)  Your guide
3. [Create VNets](tasks/CREATE_VNETS)  Specific how-to
4. [CLI Reference](reference/CLI_REFERENCE)  Command lookup

---

###  **Operator / SRE**

You deploy, monitor, and troubleshoot the Network Provider in production.

 Start here: [**For Operators**](guides/FOR_OPERATORS)

**Quick path:**
1. [Installation](setup/INSTALLATION)  Prerequisites
2. [Production Deployment](setup/PRODUCTION_DEPLOYMENT)  For ops
3. [For Operators](guides/FOR_OPERATORS)  Operational guide
4. [Troubleshooting](reference/TROUBLESHOOTING)  Debug issues

---

###  **Network Architect**

You design multi-cluster deployments, BGP routing, and site-to-site connectivity.

 Start here: [**For Network Architects**](guides/FOR_NETWORK_ARCHITECTS)

**Quick path:**
1. [Architecture](concepts/ARCHITECTURE)  System design
2. [Multi-Cluster Design](concepts/MULTI_CLUSTER)  3-cluster model
3. [For Architects](guides/FOR_NETWORK_ARCHITECTS)  Your guide
4. [BGP Setup](setup/BGP_VLAN_SETUP)  Router config

---

## Common Scenarios

### Scenario: Deploy a web application with external access

```
1. Read:   Quickstart  For K8s Users
2. Do:     Create VNet  Deploy app  Expose as LoadBalancer
3. Result: Service gets VLAN IP automatically (e.g., 10.200.0.50)
4. Access: curl http://10.200.0.50
```

 Full guide: [Expose Services](tasks/EXPOSE_WITH_LB)

---

### Scenario: Multi-subscription peering

```
1. Read:   Multi-Tenancy Model  For API Users
2. Do:     Create VNets in each subscription  Create peering
3. Result: Pods can communicate across subscriptions
4. Verify: Policy created  DNS resolves  Traffic flows
```

 Full guide: [Setup Peering](tasks/SETUP_PEERING)

---

### Scenario: Set up production deployment

```
1. Read:   Architecture  Installation  Production Deployment
2. Do:     Configure clusters  Deploy Provider  Setup BGP
3. Result: Multi-cluster network with HA and failover
4. Verify: Health checks  Traffic tests  Monitoring
```

 Full guide: [Production Deployment](setup/PRODUCTION_DEPLOYMENT)

---

## File Structure

```
docs/
 README.md (this file)

 concepts/              # Understand the platform
    OVERVIEW.md
    ARCHITECTURE.md
    MULTI_TENANCY.md
    MULTI_CLUSTER.md
    NETWORK_ISOLATION.md

 tutorials/             # Try the platform
    01-QUICKSTART.md
    02-MULTI_TIER_APP.md
    03-MULTI_SUBSCRIPTION.md
    04-VLAN_EXPOSURE.md

 setup/                 # Deploy & configure
    INSTALLATION.md
    CONFIGURATION.md
    BGP_VLAN_SETUP.md
    PRODUCTION_DEPLOYMENT.md
    SECURITY.md

 tasks/                 # Learn how to...
    CREATE_VNETS.md
    SETUP_PEERING.md
    EXPOSE_WITH_LB.md
    SETUP_PRIVATE_LINK.md
    MANAGE_NSGS.md
    MONITOR_IPS.md
    SCALE_CLUSTERS.md
    MONITORING.md

 reference/             # Look it up
    API_REFERENCE.md
    CLI_REFERENCE.md
    GLOSSARY.md
    TROUBLESHOOTING.md
    IPAM_GUIDE.md

 guides/                # Audience-specific paths
     FOR_K8S_DEVELOPERS.md
     FOR_ITL_API_USERS.md
     FOR_OPERATORS.md
     FOR_NETWORK_ARCHITECTS.md
```

---

## Quick Navigation

**By user type:**
- Kubernetes developer?  [FOR_K8S_DEVELOPERS.md](guides/FOR_K8S_DEVELOPERS)
- ITL API user?  [FOR_ITL_API_USERS.md](guides/FOR_ITL_API_USERS)
- Operator?  [FOR_OPERATORS.md](guides/FOR_OPERATORS)
- Network architect?  [FOR_NETWORK_ARCHITECTS.md](guides/FOR_NETWORK_ARCHITECTS)

**By task:**
- Create a VNet  [CREATE_VNETS.md](tasks/CREATE_VNETS)
- Expose a service  [EXPOSE_WITH_LB.md](tasks/EXPOSE_WITH_LB)
- Setup peering  [SETUP_PEERING.md](tasks/SETUP_PEERING)
- Troubleshoot  [TROUBLESHOOTING.md](reference/TROUBLESHOOTING)

**By role:**
- I deploy apps  [Quickstart](tutorials/01-QUICKSTART)
- I build infrastructure  [BGP_VLAN_SETUP.md](setup/BGP_VLAN_SETUP)
- I need API docs  [API_REFERENCE.md](reference/API_REFERENCE)

---

## Getting Help

- **Quick questions?** Check [TROUBLESHOOTING.md](reference/TROUBLESHOOTING)
- **Command syntax?** See [CLI_REFERENCE.md](reference/CLI_REFERENCE)
- **API endpoints?** Visit [API_REFERENCE.md](reference/API_REFERENCE)
- **Need a term defined?** Check [GLOSSARY.md](reference/GLOSSARY)
- **Still stuck?** Open an issue on GitHub

---

## Key Features

[x] **Azure-style networking**  VNets, subnets, NSGs, load balancers  
[x] **Multi-tenant isolation**  Namespace-based with Cilium policies  
[x] **Direct VLAN IPs**  BGP advertises external IPs automatically  
[x] **Multi-cluster resilience**  Deploy to storage, data, compute clusters  
[x] **ClusterMesh routing**  Pods communicate across clusters  
[x] **Overlapping CIDRs**  Same 10.0.0.0/16 in different subscriptions  
[x] **Cross-subscription peering**  Network policies bridge subscriptions  
[x] **Private Link**  Endpoint-based service exposure  
[x] **REST API**  Full ITL ControlPlane integration  

---

**Last Updated:** June 2026  
**Current Version:** 0.1.0  
**Status:** Production Ready
