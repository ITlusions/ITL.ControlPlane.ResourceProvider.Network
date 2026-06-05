# Overview: ITL Network Provider

What is the Network Provider and why you need it?

---

## The Problem

Running Azure-style networking on Kubernetes is complex:
- **IP Management** — How do you allocate IPs across clusters?
- **Multi-Tenancy** — How do you isolate subscriptions safely?
- **Overlapping CIDRs** — What if two customers need 10.0.0.0/16?
- **External Access** — How do you expose services to your physical network?
- **Policy Enforcement** — How do you implement NSGs in Kubernetes?

Traditional solutions (Helm charts, raw manifests) require deep Kubernetes expertise.

---

## The Solution: Network Provider

The **ITL Network Provider** is a FastAPI microservice that translates **Azure Resource Manager (ARM) API concepts** into **Cilium Kubernetes abstractions**.

```
You (REST API)
    ↓
"Create VNet 10.0.0.0/16"
    ↓
Network Provider
    ├─ Parses ARM-style request
    ├─ Validates CIDR against subscription
    ├─ Generates Cilium resources
    └─ Deploys to all 3 clusters
    ↓
Result: VNet ready to use, IP isolation guaranteed
```

---

## Key Capabilities

### 1. **Azure-Compatible API**

Use familiar Azure patterns — VNets, Subnets, NSGs, Load Balancers:

```bash
# Create a VNet (Azure-style)
curl -X POST /subscriptions/sub-001/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet1 \
  -d '{"properties": {"addressSpace": ["10.0.0.0/16"]}}'

# Same pattern for NSGs, Load Balancers, Application Gateways, etc.
```

### 2. **Multi-Tenant Isolation**

Each subscription gets its own namespace → complete isolation:

```
Subscription A (sub-001) → Namespace: sub-001 → 10.0.0.0/16
Subscription B (sub-002) → Namespace: sub-002 → 10.0.0.0/16 (same CIDR, no conflict!)
Subscription C (sub-003) → Namespace: sub-003 → 10.0.0.0/16 (still no conflict!)

Why no conflict? Kubernetes namespaces provide complete network isolation.
```

### 3. **Direct VLAN IP Assignment**

Services automatically get routable IPs from your physical network:

```
Your Network (VLAN 100)        Kubernetes (Cilium)
10.200.0.0/24                 10.0.0.0/16 (internal)
├─ Router (10.200.0.1)        └─ Pods running...
├─ LoadBalancer → 10.200.0.50 ←─ Gets external IP via BGP!
└─ API → 10.200.0.51          ←─ Direct routing, no load, no NAT!

Access from network: curl http://10.200.0.50 ✓ Direct access!
```

### 4. **Multi-Cluster Deployment**

Deploy to 3 clusters simultaneously with automatic failover:

```
Storage Cluster ──┐
                  ├─ Same VNet deployed
Data Cluster ─────┤─ Pod-to-pod works across clusters (ClusterMesh)
                  │─ Cluster down? Traffic redirects automatically
Compute Cluster ──┘
```

### 5. **Security & Policies**

Network Security Groups (NSGs) translate to Cilium policies:

```
NSG Rule: Allow HTTP from 10.0.0.0/24
    ↓
Cilium Policy: Ingress from 10.0.0.0/24 on port 80
    ↓
Result: Only pods in that CIDR can access your service
```

---

## How It Works (30,000 feet)

### Request Flow

```
1. Client Request (REST API)
   POST /subscriptions/{sub}/resourceGroups/{rg}/providers/...virtualNetworks/{vnet}

2. Network Provider validates:
   ✓ Subscription exists
   ✓ CIDR not used in this subscription
   ✓ User has permissions

3. Generate Cilium manifests:
   ├─ CiliumLoadBalancerIPPool (for IP allocation)
   ├─ Namespace (for isolation)
   └─ Labels (for multi-cluster discovery)

4. Deploy to 3 clusters (parallel):
   ├─ Create/patch storage cluster
   ├─ Create/patch data cluster
   └─ Create/patch compute cluster

5. Database record created:
   └─ Track resource metadata, audit log

6. Response to client:
   └─ HTTP 201 + VNet resource object
```

### Behind the Scenes

```
Network Provider
├─ FastAPI handlers (ARM-style routes)
├─ Cilium abstraction layer
│  ├─ Creates CiliumLoadBalancerIPPools
│  ├─ Manages CiliumNetworkPolicies
│  └─ Handles CiliumBGPPeeringPolicies
├─ Kubernetes client (async)
│  └─ Connects to 3 clusters simultaneously
├─ PostgreSQL (async SQLAlchemy)
│  └─ Stores metadata & audit logs
└─ Health checks
   └─ Monitors all 3 cluster connections
```

---

## Use Cases

### 1. **Multi-Tenant SaaS Platform**

Multiple customers, each with their own subscription:

```
Customer A (sub-aaa) → Namespace sub-aaa → VNet 10.0.0.0/16 → VLAN IP 10.200.0.50
Customer B (sub-bbb) → Namespace sub-bbb → VNet 10.0.0.0/16 → VLAN IP 10.200.0.51
Customer C (sub-ccc) → Namespace sub-ccc → VNet 10.1.0.0/16 → VLAN IP 10.200.0.52

All running on same clusters, completely isolated!
```

### 2. **Enterprise Cloud Migration**

Migrate existing Azure workloads to Kubernetes:

```
Cloud Migration Path:
  1. Deploy Network Provider → Familiar Azure API
  2. Developers use same ARM templates/tools
  3. Services work identically to Azure
  4. Same firewall rules (NSGs)
  5. Same naming conventions
  
No rewrite needed! Drop-in replacement!
```

### 3. **High-Availability Multi-Cluster**

Distribute workloads across clusters with automatic failover:

```
Region A (Storage Cluster) ┐
                           ├─ Same VNet, same policies
Region B (Data Cluster)    ├─ Pod-to-pod works across clusters
                           │─ Single point of failure? None!
Region C (Compute) ────────┘
```

---

## Who Should Use This?

| Role | Benefit |
|---|---|
| **Platform Engineers** | Manage multi-tenant networking without complexity |
| **Cloud Architects** | Design Azure-compatible Kubernetes clusters |
| **DevOps Teams** | Use familiar ARM patterns instead of raw K8s YAML |
| **Enterprise IT** | Migrate existing Azure workloads seamlessly |
| **SaaS Providers** | Isolate customer networks safely and cost-effectively |

---

## What Makes It Different?

### vs. Kubernetes Ingress

| Feature | Network Provider | K8s Ingress |
|---|---|---|
| Multi-tenant isolation | ✅ Namespace-level | ⚠️ Requires additional policies |
| Overlapping CIDRs | ✅ Safe in different namespaces | ❌ Conflicts within cluster |
| External IP via BGP | ✅ Automatic | ❌ Requires external controller |
| NSGs / Network policies | ✅ Built-in | ⚠️ Manual CiliumNetworkPolicy |
| Azure compatibility | ✅ Exact API match | ❌ Not Azure-compatible |

### vs. Azure itself

| Feature | Network Provider | Azure |
|---|---|---|
| Cost | ✅ Run on-prem or any cloud | ❌ Azure billing |
| Portability | ✅ Works on any K8s | ❌ Azure-only |
| Multi-cluster | ✅ Across datacenters | ⚠️ Single region |
| Familiar API | ✅ 100% Azure ARM | ✅ Same as Azure |

---

## Typical Workflow

### Day 1: Setup

```bash
# 1. Deploy Network Provider to 3 clusters
docker-compose up -d

# 2. Verify health
curl http://localhost:8002/health

# 3. Test with hello-world VNet
itlc resource create --resource-type virtualNetworks ...
```

### Day 2: Create Infrastructure

```bash
# 1. Create VNet
itlc resource create --resource-type virtualNetworks --resource-name prod-vnet ...

# 2. Create Subnets
itlc resource create --resource-type "virtualNetworks/subnets" --resource-name frontend ...

# 3. Create NSG
itlc resource create --resource-type networkSecurityGroups --resource-name frontend-nsg ...

# 4. Deploy app
kubectl create deployment web --image=nginx

# 5. Expose via LoadBalancer
kubectl expose deployment web --type=LoadBalancer --port=80
# Gets external IP automatically!
```

### Day 3+: Operate & Scale

```bash
# Monitor IPs
itlc resource list --resource-type loadBalancers

# Add more replicas
kubectl scale deployment web --replicas=5

# Scale to more pods? VNet handles it automatically!
```

---

## Next Steps

- **Want to understand the design?** → [Architecture](ARCHITECTURE.md)
- **Ready to try it?** → [Quickstart](../tutorials/01-QUICKSTART.md)
- **Need specific how-tos?** → [For Kubernetes Users](../guides/FOR_K8S_DEVELOPERS.md) or [For API Users](../guides/FOR_ITL_API_USERS.md)
- **Setting up production?** → [Production Deployment](../setup/PRODUCTION_DEPLOYMENT.md)

---

**Last Updated:** June 2026
