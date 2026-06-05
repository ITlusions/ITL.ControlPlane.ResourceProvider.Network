# Network Provider Architecture

## System Overview

The Network Provider is a Python FastAPI microservice that implements Azure-style networking abstractions on top of Cilium SDN running on Talos/Kubernetes clusters.

### Tenant & Subscription Hierarchy

- **Tenant** = Keycloak Realm (top-level organization)
- **Subscription** = Billing/resource container within a tenant (e.g., `sub-00000001`)
- Each subscription gets its own Kubernetes namespace for complete isolation
- Multiple subscriptions can safely use overlapping CIDRs (e.g., both use 10.0.0.0/16) due to namespace isolation

```

                    FastAPI (port 8002)                         
              Network Provider Application                       

 Routes Layer (ARM-style resource paths)                         
 /subscriptions/{sub}/resourceGroups/{rg}/providers/.../...     

 Resource Handler Layer                                         
 - VNet Handler           - NSG Handler       - Load Balancer    
| - Subnet Handler         - NIC Handler       - Application Gw    |
| - Public IP Handler      - Peering Handler   - BGP Policy       |
| - Private Link Service   - Private Endpoint  - Private DNS       |

 Cilium Abstraction Layer                                       
 - CiliumLoadBalancerIPPool (for VNets/Subnets)                 
 - CiliumNetworkPolicy (for NSGs/Peering/Private Links)         
 - CiliumBGPPeeringPolicy (for multi-site)                      
 - K8s Services (for Load Balancers, Private Link DNS)          

 Multi-Cluster Interface                                        
 - Storage Cluster API    - Data Cluster API    - Compute API   
 - ClusterMesh Coordination (cross-cluster routing)             

 PostgreSQL Persistence Layer (async SQLAlchemy)                
 - Resource metadata, audit logs, state tracking                

```

## Data Flow

### Create Virtual Network

```
1. Client Request (REST API)
   POST /subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/vnet-prod
   Body: { "properties": { "addressSpace": ["10.0.0.0/16"] } }

2. NetworkProvider._create_vnet()
    Extract subscription_id from resource_id
    Generate subscription_namespace: "sub-00000001"
    Generate K8s_name: _generate_k8s_name(resource_id, "pool")  "pool-a1b2c3d4"
    Create Cilium pool manifest

3. _apply_cilium_pool_all_clusters()
    Check if pool exists in storage cluster
    Patch if exists, create if not
    Deploy to data cluster
    Deploy to compute cluster

4. _setup_clustermesh()
    Register clusters for cross-cluster routing

5. PostgreSQL (async insert)
    Store VirtualNetwork metadata

6. Response to Client
    HTTP 201 + VirtualNetwork object
```

### Create Network Security Group (NSG)

```
1. Client Request
   POST /subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/networkSecurityGroups/nsg-frontend
   Body: { "securityRules": [...] }

2. NetworkProvider._create_nsg()
    Extract subscription_namespace, K8s_name
    Convert security rules to Cilium L3/L4 policy
    Build CiliumNetworkPolicy manifest

3. _apply_cilium_policy_all_clusters()
    Deploy to storage cluster
    Deploy to data cluster
    Deploy to compute cluster

4. PostgreSQL
    Store NSG metadata

5. Response
    HTTP 201 + NSG object
```

### VNet Peering

```
1. Client Request
   POST /subscriptions/sub-00000001/.../virtualNetworkPeerings/peering-prod-dev
   Body: {
       "properties": {
           "remoteVirtualNetwork": { "id": "/subscriptions/sub-00000002/.../vnet-prod" },
           "allowVirtualNetworkAccess": true
       }
   }

2. NetworkProvider._create_vnet_peering()
    Extract local_subscription_id (sub-00000001)
    Extract remote_subscription_id from remote vnet (sub-00000002)
    Create CiliumNetworkPolicy:
     - Name: "peer-{hash}"
     - Namespace: "sub-00000001" (local subscription)
     - Allows ingress from "sub-00000002" namespace
     - Allows egress to "sub-00000002" if allowForwardedTraffic=true
    Deploy policy to all clusters

3. Result
    Pods in subscription sub-00000001 can now communicate with pods in subscription sub-00000002
```

## Multi-Cluster Architecture

### Cluster Topology

```
        
 Storage Cluster          Data Cluster             Compute Cluster  
                                                                    
              
  Cilium (SDN)           Cilium (SDN)           Cilium (SDN)  
  - Networking           - Networking           - Networking  
  - Load Balance         - Load Balance         - LB          
              
                                                                    
 Namespace:               Namespace:               Namespace:       
  sub-00000001          sub-00000001          sub-00000001 
  sub-00000002          sub-00000002          sub-00000002 
  kube-system           kube-system           kube-system  
                                                                    
 Env:                     Env:                     Env:             
 - HOSTNAME=storage       - HOSTNAME=data          - HOSTNAME=compute
 - CLUSTER_NAME=s         - CLUSTER_NAME=d         - CLUSTER_NAME=c
        
                                                             
                                                             
         
         
              ClusterMesh (Cilium peering)
               Pod-to-pod routing across clusters
               Service discovery cross-cluster
               Distributed load balancing
```

### Deployment Pattern (Multi-Cluster Fanout)

When creating a resource, the Network Provider deploys to **all clusters**:

```python
async def _create_vnet(resource_id, ...):
    # 1. Create pool in storage cluster
    storage_api.create_namespaced_custom_object(
        manifest,
        namespace=subscription_ns,  # E.g., "sub-00000001"
        ...
    )
    
    # 2. Create pool in data cluster
    data_api.create_namespaced_custom_object(
        manifest,
        namespace=subscription_ns,
        ...
    )
    
    # 3. Create pool in compute cluster
    compute_api.create_namespaced_custom_object(
        manifest,
        namespace=subscription_ns,
        ...
    )
    
    # 4. Setup cross-cluster routing
    await _setup_clustermesh([storage, data, compute])
```

**Result:** VNets appear in all three clusters, pods can communicate transparently.

---

## Next Steps

- **More on multi-tenancy?**  [Multi-Tenancy Model](MULTI_TENANCY.md)
- **Multi-cluster details?**  [Multi-Cluster Design](MULTI_CLUSTER.md)
- **Ready to deploy?**  [Installation](../setup/INSTALLATION.md)

---

**Last Updated:** June 2026
