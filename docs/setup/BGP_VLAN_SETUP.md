# BGP + VLAN Setup Guide

Complete walkthrough for configuring BGP peering and VLAN-based load balancer IPs across your 3 Kubernetes clusters.

---

## Architecture Overview

```

 Your Physical Network                                      
                                                             
  Core Router (10.1.1.1)                                    
   VLAN 100 (Storage): 10.200.0.0/24                     
   VLAN 200 (Data):    10.201.0.0/24                     
   VLAN 300 (Compute): 10.202.0.0/24                     
                                                             

         BGP peering (AS 65000/65001/65002)
        
    
                                     
                                     
    
 Storage        Data            Compute      
 Cluster        Cluster         Cluster      
 AS: 65000      AS: 65001       AS: 65002    
 VLAN 100       VLAN 200        VLAN 300     
 10.200.0.0/    10.201.0.0/     10.202.0.0/  
 25             25              25           
    
```

---

## Prerequisites

- [x] 3 Kubernetes clusters (Talos HardenedOS preferred)
- [x] Cilium v1.14+ installed on all clusters
- [x] Router with BGP support (Cisco, Juniper, Arista, etc.)
- [x] Network connectivity between clusters and router
- [x] kubectl access to all clusters
- [x] Understanding of BGP basics

---

## Phase 1: Router Configuration

### Cisco Example

```cisco
! Enable BGP
router bgp 65200
  bgp router-id 10.1.1.1
  bgp log-neighbor-changes
  
  ! Define neighbor relationships with each cluster
  neighbor 10.0.0.1 remote-as 65000      # Storage cluster node 1
  neighbor 10.0.1.1 remote-as 65001      # Data cluster node 1
  neighbor 10.0.2.1 remote-as 65002      # Compute cluster node 1
  
  ! Configure address families
  address-family ipv4 unicast
    neighbor 10.0.0.1 activate
    neighbor 10.0.1.1 activate
    neighbor 10.0.2.1 activate
    
    ! Advertise VLAN subnets to clusters
    network 10.200.0.0 mask 255.255.255.0   # VLAN 100 (Storage)
    network 10.201.0.0 mask 255.255.255.0   # VLAN 200 (Data)
    network 10.202.0.0 mask 255.255.255.0   # VLAN 300 (Compute)
    
    ! Accept routes from clusters
    maximum-paths 2 eibgp
  exit-address-family
exit
```

---

## Phase 2: Cilium BGP Configuration

### Step 1: Label Cilium Nodes for BGP

```bash
# Label nodes in Storage cluster (AS 65000)
kubectl --context=storage-cluster label nodes \
  --all bgp-enabled=true bgp-asn=65000 cilium.io/bgp=true

# Label nodes in Data cluster (AS 65001)
kubectl --context=data-cluster label nodes \
  --all bgp-enabled=true bgp-asn=65001 cilium.io/bgp=true

# Label nodes in Compute cluster (AS 65002)
kubectl --context=compute-cluster label nodes \
  --all bgp-enabled=true bgp-asn=65002 cilium.io/bgp=true

# Verify labels
kubectl get nodes --show-labels | grep bgp
```

### Step 2: Create BGP Peering Policy

```yaml
# storage-cluster/cilium-bgp-policy.yaml
apiVersion: cilium.io/v2alpha1
kind: CiliumBGPPeeringPolicy
metadata:
  name: itl-bgp-peering
  namespace: kube-system
spec:
  nodeSelector:
    matchLabels:
      bgp-enabled: "true"
  
  virtualRouters:
    - localASN: 65000
      serviceSelector:
        matchExpressions:
          - key: expose
            operator: In
            values: ["external"]
      
      neighbors:
        - peerAddress: 10.1.1.1
          peerASN: 65200
          gracefulRestart:
            enabled: true
            restartTimeSeconds: 120
          timers:
            connectRetryMs: 120000
            holdTimeSeconds: 9
            keepAliveTimeSeconds: 3
```

---

## Next Steps

- **Ready to deploy?**  [Installation](INSTALLATION.md)
- **Security?**  [Security Best Practices](SECURITY.md)

---

**Last Updated:** June 2026
