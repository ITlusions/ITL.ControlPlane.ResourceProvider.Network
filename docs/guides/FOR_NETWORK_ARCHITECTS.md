# Guide for Network Architects

Designing and planning network infrastructure with Network Provider.

---

## Architecture Patterns

### Pattern 1: Multi-Tenant SaaS

```
┌─────────────────────────────────────────┐
│ SaaS Platform                           │
├─────────────────────────────────────────┤
│                                         │
│ Tenant 1 (acme.com)                     │
│ ├─ Sub: acme-prod (10.0.0.0/16)         │
│ ├─ Sub: acme-staging (10.0.0.0/16)      │
│ ├─ Namespace isolation per sub          │
│ └─ Cross-region failover                │
│                                         │
│ Tenant 2 (widgets.corp)                 │
│ ├─ Sub: widgets-prod (10.1.0.0/16)      │
│ ├─ Sub: widgets-dev (10.1.0.0/16)       │
│ ├─ Namespace isolation per sub          │
│ └─ Independent scaling                  │
│                                         │
│ Shared Services (platform.local)        │
│ ├─ Sub: shared-prod                     │
│ ├─ Metrics, logging, DNS               │
│ └─ Accessible to all tenants (peering)  │
│                                         │
└─────────────────────────────────────────┘
```

**Key Decisions:**
- ✅ One subscription per tenant environment
- ✅ Overlapping CIDRs (namespace isolation handles it)
- ✅ Peering for cross-tenant communication to shared services
- ✅ Quota enforcement per subscription

**Networking:**
```
Tenant 1: 10.0.0.0/16 (internal)
  → VLAN IP: 10.200.0.50 (external)
  → Internet: All external traffic uses this IP

Tenant 2: 10.1.0.0/16 (internal)
  → VLAN IP: 10.201.0.50 (external)
  → Internet: All external traffic uses this IP

Shared Services: 10.100.0.0/16
  → VLAN IP: 10.200.0.100 (for internal access)
  → Private Link endpoints allow tenant access
```

---

### Pattern 2: Enterprise Multi-Region

```
┌──────────────────────────────────────────────────────┐
│ Global Enterprise Network                            │
├──────────────────────────────────────────────────────┤
│                                                      │
│ Region 1 (US-East)                                  │
│ ├─ Storage Cluster (zone-a, zone-b, zone-c)        │
│ ├─ Data Cluster (zone-a, zone-b)                   │
│ ├─ Compute Cluster (zone-a, zone-b, zone-c)        │
│ ├─ VNets: 10.0.0.0/16                              │
│ └─ VLAN: 10.200.0.0/24                             │
│                                                      │
│ Region 2 (EU-West)                                  │
│ ├─ Storage Cluster (zone-a, zone-b, zone-c)        │
│ ├─ Data Cluster (zone-a, zone-b)                   │
│ ├─ Compute Cluster (zone-a, zone-b, zone-c)        │
│ ├─ VNets: 10.0.0.0/16 (same CIDR, different region)│
│ └─ VLAN: 10.201.0.0/24                             │
│                                                      │
│ Region 3 (APAC)                                     │
│ └─ (Similar setup)                                  │
│                                                      │
└──────────────────────────────────────────────────────┘
                         │
                    Global peering
                  (cross-region VNet peering)
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
            US-East   EU-West    APAC
```

**Key Decisions:**
- ✅ Separate Network Provider instance per region
- ✅ Same CIDR ranges (namespace + region isolation)
- ✅ Global peering for cross-region communication
- ✅ Regional failover (global LB routes to healthy region)

**Networking:**
```
Subscription in US-East:  10.0.0.0/16 → 10.200.0.50
Subscription in EU-West:  10.0.0.0/16 → 10.201.0.50
(No conflict due to region isolation)

Cross-region access:
├─ EU pod wants US data → Peering allows 10.0.0.0/16 → 10.0.0.0/16
├─ Traffic routed via global WAN link
└─ Automatic failover if link down (DNS redirects to regional endpoint)
```

---

### Pattern 3: Hub-and-Spoke

```
┌─────────────────────────────────────┐
│ Hub (Shared Services)               │
│ VNet: 10.100.0.0/16                 │
│ ├─ DNS: 10.100.0.10                 │
│ ├─ Logging: 10.100.0.20              │
│ ├─ Registry: 10.100.0.30             │
│ └─ Bastion: 10.100.0.40              │
└────────────┬────────────────────────┘
             │
    ┌────────┼────────┬────────┐
    ▼        ▼        ▼        ▼
  Spoke1   Spoke2   Spoke3   Spoke4
  10.0.0   10.1.0   10.2.0   10.3.0
  (Dev)    (Staging) (Prod-A) (Prod-B)
```

**Peering Setup:**
```bash
# Hub can reach all spokes
Hub → Spoke1: Allow 10.100.0.0/16 → 10.0.0.0/16
Hub → Spoke2: Allow 10.100.0.0/16 → 10.1.0.0/16
Hub → Spoke3: Allow 10.100.0.0/16 → 10.2.0.0/16
Hub → Spoke4: Allow 10.100.0.0/16 → 10.3.0.0/16

# Spokes can reach hub
Spoke1 → Hub: Allow 10.0.0.0/16 → 10.100.0.0/16
Spoke2 → Hub: Allow 10.1.0.0/16 → 10.100.0.0/16
Spoke3 → Hub: Allow 10.2.0.0/16 → 10.100.0.0/16
Spoke4 → Hub: Allow 10.3.0.0/16 → 10.100.0.0/16

# Spokes can NOT reach each other (security by default)
```

**Benefits:**
- ✅ Hub provides shared services (DNS, logging, etc.)
- ✅ Spokes isolated from each other
- ✅ Easy to add new spokes
- ✅ Centralized security policies

---

## CIDR Planning

### Calculating CIDR Requirements

```
Subscription Format: 10.0.0.0/16 (65,536 IPs)

For 100 subscriptions:
├─ Option 1: Overlapping CIDRs (namespace isolation)
│  └─ Use 10.0.0.0/16 for all (requires namespace separation)
│
├─ Option 2: Non-overlapping CIDRs (if per-customer security requirement)
│  ├─ Sub1: 10.0.0.0/16
│  ├─ Sub2: 10.1.0.0/16
│  ├─ Sub3: 10.2.0.0/16
│  └─ ... (need 100 × /16 = 100 × 65K = 6.5M IPs)
│
└─ Recommendation: Use overlapping + namespace isolation
   └─ More efficient, scales better
```

### Subnet Sizing

```
VNet: 10.0.0.0/16 (65,536 IPs)

Subnets:
├─ Frontend tier: 10.0.0.0/24 (256 IPs)
│  └─ Expected pods: 50-100
│
├─ Application tier: 10.0.1.0/22 (1,024 IPs)
│  └─ Expected pods: 200-500
│
├─ Database tier: 10.0.5.0/24 (256 IPs)
│  └─ Expected pods: 10-20
│
├─ Batch jobs: 10.0.6.0/23 (512 IPs)
│  └─ Expected pods: 100-200
│
└─ Reserved for growth: 10.0.8.0/21 (2,048 IPs)
   └─ Keep 30% of VNet unallocated for growth
```

### IP Pool Sizing

```
For VLAN IP allocation:

Total needed: Number of LoadBalancers × clusters + buffer
Example:
├─ Estimated LBs: 20
├─ Clusters: 3
├─ Per cluster: 20 / 3 ≈ 7 LBs
├─ Buffer (20% growth): 7 × 1.2 = 8-9 per cluster
├─ Per cluster allocation: 10.200.0.0/25 (128 IPs) provides 127 usable
└─ Total: 3 clusters × 127 IPs = 381 IPs available

Remaining VLANs for future growth: 10.200.0.128/25, 10.201.0.0/24, etc.
```

---

## Security Architecture

### Network Segmentation

```
┌─────────────────────────────────────┐
│ Kubernetes Cluster                  │
├─────────────────────────────────────┤
│                                     │
│ Subscription: sub-prod              │
│ ├─ Namespace: sub-prod              │
│ │                                   │
│ │ ┌─────────────────────────────┐  │
│ │ │ Frontend Tier               │  │
│ │ │ NSG: Allow 80, 443 from ext │  │
│ │ ├─ web-1 (10.0.0.1)           │  │
│ │ ├─ web-2 (10.0.0.2)           │  │
│ │ └─ web-3 (10.0.0.3)           │  │
│ │ └─────────────────────────────┘  │
│ │           ↓ Internal only         │
│ │ ┌─────────────────────────────┐  │
│ │ │ Application Tier            │  │
│ │ │ NSG: Allow from frontend    │  │
│ │ ├─ api-1 (10.0.1.1)           │  │
│ │ ├─ api-2 (10.0.1.2)           │  │
│ │ └─ api-3 (10.0.1.3)           │  │
│ │ └─────────────────────────────┘  │
│ │           ↓ Internal only         │
│ │ ┌─────────────────────────────┐  │
│ │ │ Database Tier               │  │
│ │ │ NSG: Allow only from app    │  │
│ │ └─ db-1 (10.0.5.1)            │  │
│ │ └─────────────────────────────┘  │
│ │                                   │
│ └─ No cross-tier shortcuts!         │
│                                     │
└─────────────────────────────────────┘
```

**NSG Rules:**
```
Frontend → Internet:
  ├─ Allow inbound: 80 (HTTP), 443 (HTTPS)
  ├─ Allow outbound: 443 (HTTPS to app tier)
  └─ Deny all else

App → Database:
  ├─ Allow inbound: 5432 (PostgreSQL)
  ├─ Allow outbound: 443 (HTTPS for external APIs)
  └─ Deny all else

Database → Nowhere:
  ├─ Allow inbound: Only from app tier
  ├─ Deny all outbound (stateful — responses allowed)
  └─ No backup exports to internet!
```

---

## Capacity & Performance

### Performance Targets

```
API Latency:
├─ p50: < 50ms
├─ p95: < 200ms
└─ p99: < 500ms

Throughput:
├─ Requests/sec: 1,000+ per node
├─ Pods per cluster: 1,000+
└─ Resources per subscription: 10,000+

Availability:
├─ Uptime: 99.95% (4.4 hrs downtime/year)
├─ RTO: < 15 minutes
└─ RPO: < 1 hour
```

### Growth Forecasting

```
Assumptions:
├─ 50 new subscriptions/month
├─ 50 VNets per subscription
├─ 100 subnets per VNet
└─ 10 NSGs per subnet

Year 1 Growth:
├─ Month 1: 50 subs, 2,500 VNets, 250K subnets
├─ Month 6: 300 subs, 15K VNets, 1.5M subnets
└─ Month 12: 600 subs, 30K VNets, 3M subnets

Scaling triggers:
├─ At 70% database capacity → Add replica
├─ At 70% API latency budget → Add replicas to Network Provider
├─ At 70% IP pool usage → Add new VLAN
└─ At 70% cluster node usage → Add nodes or new cluster
```

---

## Disaster Recovery Planning

### RTO/RPO Analysis

```
Scenario 1: Single cluster fails
├─ Detection: ~2 minutes (health check)
├─ Impact: Customers lose access to resources in that cluster
├─ RTO: < 5 minutes (traffic reroutes to other clusters via BGP)
├─ RPO: 0 (multi-cluster replication)
└─ Action: Automatic (no manual intervention)

Scenario 2: Complete data loss (all clusters)
├─ Detection: Immediate (all clusters unreachable)
├─ Impact: Complete platform outage
├─ RTO: 15-30 minutes (restore database from backup)
├─ RPO: 1 hour (last backup)
└─ Action: Manual data restoration

Scenario 3: Database corruption
├─ Detection: Application errors (consistency checks)
├─ Impact: Unknown (could affect random resources)
├─ RTO: 15 minutes (restore database)
├─ RPO: 1 hour (last known good backup)
└─ Action: Restore, verify, investigate cause

Scenario 4: Security breach
├─ Detection: Audit logs show unauthorized access
├─ Impact: Customer data may be compromised
├─ RTO: Depends on containment (could be hours)
├─ RPO: Full audit log (days to weeks)
└─ Action: Investigate, notify customers, remediate
```

### DR Drill Schedule

```
Monthly: Restore backup to test environment
├─ Verify data integrity
├─ Test failover process
└─ Train team

Quarterly: Full DR simulation
├─ Simulate cluster failure
├─ Reroute traffic
├─ Verify all systems operational

Annual: Complete outage drill
├─ All clusters offline
├─ Restore from backup
├─ Verify all customer data accessible
└─ Post-incident review
```

---

## Compliance & Governance

### Regional Data Residency

```
Regulation: GDPR (EU customers)
Requirement: Data stays in EU
Solution:
├─ Run EU-West region Network Provider instance
├─ All subscriptions for EU customers use EU clusters only
├─ Cross-region peering disabled for EU customers
└─ Audit trail: Track all data access

Regulation: HIPAA (Healthcare data)
Requirement: Encryption, audit logs, access control
Solution:
├─ Enable mTLS for pod-to-pod communication
├─ Enable encryption at rest (PostgreSQL)
├─ Audit all resource changes
├─ RBAC restricts to authorized personnel
└─ Annual compliance audit

Regulation: SOC 2 (Availability, Security)
Requirement: Documented controls
Solution:
├─ Multi-cluster architecture (availability)
├─ Network policies enforce isolation (security)
├─ Audit logs prove changes (change management)
├─ Health monitoring (operational excellence)
└─ Incident response plan (documented procedures)
```

---

## Best Practices Summary

### ✅ DO:

- ✅ Plan IP ranges before deployment
- ✅ Use namespace isolation for multi-tenancy
- ✅ Implement network segmentation (tiers, subnets)
- ✅ Define NSG rules before deploying apps
- ✅ Monitor capacity trends (scale proactively)
- ✅ Test DR procedures regularly
- ✅ Document architecture decisions
- ✅ Use cross-cluster failover

### ❌ DON'T:

- ❌ Change CIDR ranges after deployment (very hard to migrate)
- ❌ Mix isolated and peered subscriptions randomly
- ❌ Create NSGs without understanding the traffic flow
- ❌ Assume one cluster can handle all load
- ❌ Ignore capacity warnings
- ❌ Deploy to production without DR testing
- ❌ Leave documentation out of date

---

## Next Steps

- **Ready to deploy?** → [Installation](../setup/INSTALLATION.md)
- **Need setup guidance?** → [Security & Best Practices](../setup/SECURITY.md)
- **Design examples?** → [Tutorials](../tutorials/)

---

**Last Updated:** June 2026
