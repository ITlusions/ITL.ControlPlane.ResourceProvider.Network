# Multi-Cluster Architecture

How Network Provider deploys to 3 clusters simultaneously and ensures resilience.

---

## The 3-Cluster Model

```

 Physical Network / Router            
 10.1.1.0/24  (BGP AS 65000)          

              BGP peering
    
                            
                            
  
Storage    Data   Compute 
Cluster  Cluster  Cluster 
                          
VLAN:100 VLAN:200 VLAN:300
10.200.  10.201.  10.202. 
  
                      
    
          ClusterMesh
          (Cilium)
```

---

## Cluster Roles

### Storage Cluster

**Purpose:** Persistent data and stateful workloads

- **VLAN:** VLAN 100 (10.200.0.0/24)
- **BGP AS:** 65000
- **Workloads:** Databases, message queues, caches
- **IP Pool:** 10.200.0.0/25 (LB IPs), 10.200.0.128/25 (Reserved)
- **Features:** 
  - Persistent volumes (storage backend)
  - Database replicas
  - State management

### Data Cluster

**Purpose:** Analytics, batch processing, data transformation

- **VLAN:** VLAN 200 (10.201.0.0/24)
- **BGP AS:** 65001
- **Workloads:** Data pipelines, analytics engines, report generation
- **IP Pool:** 10.201.0.0/25 (LB IPs)
- **Features:**
  - High CPU/memory nodes
  - Large storage allocations
  - Long-running jobs

### Compute Cluster

**Purpose:** Stateless application workloads

- **VLAN:** VLAN 300 (10.202.0.0/24)
- **BGP AS:** 65002
- **Workloads:** Web services, APIs, microservices
- **IP Pool:** 10.202.0.0/25 (LB IPs)
- **Features:**
  - Auto-scaling
  - Rapid pod turnover
  - Horizontal scaling

---

## How Multi-Cluster Deployment Works

### Single Request  3 Clusters

When you create a VNet:

```bash
# 1. Single API request
POST /subscriptions/sub-001/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet-prod
{
  "properties": {"addressSpace": ["10.0.0.0/16"]}
}

# 2. Network Provider (parallel deployment):
 Create namespace in Storage cluster
 Create CiliumLoadBalancerIPPool in Storage cluster
 Create namespace in Data cluster
 Create CiliumLoadBalancerIPPool in Data cluster
 Create namespace in Compute cluster
 Create CiliumLoadBalancerIPPool in Compute cluster

# 3. Response: 201 Created
# The VNet now exists across all 3 clusters!
```

### ClusterMesh: Transparent Cross-Cluster Networking

Once deployed, pods can communicate across clusters:

```
Pod in Storage (10.0.1.5)          Pod in Compute (10.0.2.10)
                                            
         
                    ClusterMesh
                 (Cilium service mesh)
         
Result: Pods communicate as if on same cluster!
```

---

## Multi-Cluster Load Balancer

### Scenario: App deployed across 3 clusters

```bash
# Deploy app in all 3 clusters
kubectl --kubeconfig=storage create deployment web --image=nginx
kubectl --kubeconfig=data create deployment web --image=nginx
kubectl --kubeconfig=compute create deployment web --image=nginx

# Expose as LoadBalancer (each cluster)
kubectl --kubeconfig=storage expose deployment web --type=LoadBalancer --port=80
kubectl --kubeconfig=data expose deployment web --type=LoadBalancer --port=80
kubectl --kubeconfig=compute expose deployment web --type=LoadBalancer --port=80

# Result:
# Storage Cluster:  VLAN IP 10.200.0.50
# Data Cluster:     VLAN IP 10.201.0.50
# Compute Cluster:  VLAN IP 10.202.0.50

# All 3 IPs route to the same service (via BGP advertisement)
```

### High Availability

```
User (external): curl http://10.200.0.50

Network sees 3 potential backends:
 10.200.0.50 (Storage)  Primary
 10.201.0.50 (Data)     Backup 1
 10.202.0.50 (Compute)  Backup 2

Storage cluster down?
 Router redirects via BGP to Data/Compute clusters
   No downtime!
```

---

## Failover & Resilience

### Scenario: Storage Cluster Fails

```
BEFORE:

 Network Traffic                      
  60%  Storage (10.200.0.0/24)    
  20%  Data (10.201.0.0/24)       
  20%  Compute (10.202.0.0/24)    


Storage Cluster FAILS
    

AFTER (automatic):

 Network Traffic (redirected)         
  0%  Storage (OFFLINE)           
  50%  Data (10.201.0.0/24)          Increased
  50%  Compute (10.202.0.0/24)       Increased


DNS/BGP advertisements update automatically
No manual intervention needed!
```

### ClusterMesh Health Checking

Cilium monitors each cluster:

```bash
# Check ClusterMesh status
kubectl exec -it -n kube-system ds/cilium -- cilium clustermesh status

# Output:
# Cluster | Nodes | Ready
# --------|-------|------
# storage |   5   |  5/5
# data    |   4   |  4/4
# compute |   6   |  6/6

# If a cluster fails:
# storage |   0   |  0/5 (UNREACHABLE)
```

---

## Cross-Cluster Communication

### Pod-to-Pod Communication

```
Pod in Storage (sub-001, 10.0.1.5)
    wants to talk to
Pod in Data (sub-001, 10.0.1.10)

DNS Query:  pod-name.sub-001.svc.cluster.local
    
CoreDNS: Returns 10.0.1.10 (Cilium injects cross-cluster endpoint)
    
Cilium: Routes through ClusterMesh
    
Delivers traffic to Data cluster

Result: Same namespace pod reachable across clusters!
```

### Service Discovery

```yaml
# In Storage cluster
apiVersion: v1
kind: Service
metadata:
  name: database
  namespace: sub-001
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432

---

# From any pod (any cluster):
# nslookup database.sub-001.svc.cluster.local
#  Resolves to ClusterMesh endpoint
#  Cilium routes traffic appropriately
```

---

## Multi-Cluster Network Policies

### Scenario: NSG in one cluster, applied to all

```bash
# Create NSG in subnet of sub-001
itlc resource create --resource-type networkSecurityGroups \
  --resource-name my-nsg \
  --properties '{
    "securityRules": [{
      "name": "allow-http",
      "properties": {
        "direction": "Inbound",
        "access": "Allow",
        "protocol": "TCP",
        "destinationPortRange": "80"
      }
    }]
  }'

# Network Provider creates CiliumNetworkPolicy in:
 Storage cluster namespace sub-001
 Data cluster namespace sub-001
 Compute cluster namespace sub-001

# Result: NSG rule enforced across all 3 clusters!
```

---

## Capacity Planning

### Multi-Cluster Growth

```
Phase 1: Proof of Concept
 Storage: 3 nodes
 Data: 2 nodes
 Compute: 2 nodes
Total: 7 nodes, ~350 pods

Phase 2: Production
 Storage: 5 nodes (persistent workloads)
 Data: 8 nodes (analytics scaling)
 Compute: 10 nodes (app autoscaling)
Total: 23 nodes, ~1,500 pods

Phase 3: Regional Expansion
 Add new region with 3 new clusters
 Same multi-cluster design
 Cross-region ClusterMesh (or separate ControlPlane instance)
```

### IP Pool Management

```
Storage Cluster (VLAN 100)
 LB IP Pool: 10.200.0.0/25 (128 IPs for LoadBalancers)
 Reserved: 10.200.0.128/25 (128 IPs for future growth)

Data Cluster (VLAN 200)
 LB IP Pool: 10.201.0.0/25
 Reserved: 10.201.0.128/25

Compute Cluster (VLAN 300)
 LB IP Pool: 10.202.0.0/25
 Reserved: 10.202.0.128/25

Total: 384 external IPs available
```

---

## Monitoring Multi-Cluster Health

### Health Checks

```bash
# Check all clusters
curl http://localhost:8002/health

# Output:
{
  "status": "healthy",
  "clusters": {
    "storage": "connected",     # Can reach API
    "data": "connected",
    "compute": "connected"
  },
  "database": "connected",      # PostgreSQL OK
  "version": "0.1.0"
}

# If storage cluster down:
{
  "status": "degraded",
  "clusters": {
    "storage": "unreachable",    ERROR
    "data": "connected",
    "compute": "connected"
  }
}
```

### Alerting

```bash
# Critical: Any cluster down
alert: ClusterDown
  condition: health.clusters.{cluster} == "unreachable"
  severity: P1
  action: PagerDuty

# Warning: High latency to cluster
alert: HighLatencyCluster
  condition: cluster_latency_ms > 500
  severity: P2

# Warning: Low IP pool availability
alert: IPPoolLow
  condition: (available_ips / total_ips) < 0.2
  severity: P3
```

---

## Best Practices

### Best Practices:

#### DO:

- [x] Deploy to all 3 clusters simultaneously (handled by Network Provider)
- [x] Monitor ClusterMesh status regularly
- [x] Plan IP pools with growth in mind
- [x] Test failover scenarios in staging
- [x] Use cluster affinity for stateful workloads (pin to Storage cluster)
- [x] Distribute load across clusters

### [-] DON'T:

- [-] Deploy to only 1 cluster (defeats multi-cluster benefits)
- [-] Assume one cluster can handle all traffic
- [-] Ignore ClusterMesh health warnings
- [-] Mix cluster roles (e.g., run databases on Compute cluster)
- [-] Use tiny IP pools (plan for 2x growth minimum)

---

## Troubleshooting

### Pods can't reach service in other cluster

**Check:**
```bash
# 1. Verify both clusters have the pod
kubectl --kubeconfig=storage get pods -n sub-001 | grep my-pod
kubectl --kubeconfig=data get pods -n sub-001 | grep my-pod

# 2. Check DNS resolution
kubectl --kubeconfig=compute exec -it debug-pod -n sub-001 -- \
  nslookup my-pod.sub-001.svc.cluster.local
# Should return IPs from multiple clusters

# 3. Check ClusterMesh status
kubectl --kubeconfig=storage exec -it -n kube-system ds/cilium -- cilium clustermesh status
```

### One cluster unreachable

**Check:**
```bash
# 1. Network connectivity
ping {cluster-api-endpoint}

# 2. Kubernetes API health
curl -k https://{cluster-api}:6443/healthz

# 3. Cilium status
kubectl --kubeconfig={unreachable-cluster} exec -it -n kube-system ds/cilium -- cilium status
```

---

## Next Steps

- **Ready to deploy?**  [Installation](../setup/INSTALLATION)
- **Need architecture details?**  [Architecture](ARCHITECTURE)
- **Configuring BGP?**  [BGP Setup](../setup/BGP_VLAN_SETUP)

---

**Last Updated:** June 2026
