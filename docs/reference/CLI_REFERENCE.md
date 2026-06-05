# CLI Reference

Quick reference for ITL ControlPlane CLI commands to discover and list IPs.

---

## Active Pod IPs in Subnets

```bash
# List all active IPs in a subnet
itlc resource list-ips \
  --resource-type "virtualNetworks/subnets/activeIps" \
  --vnet prod-vnet \
  --subnet prod-subnet

# Filter by tenant
itlc resource list-ips \
  --vnet prod-vnet \
  --subnet prod-subnet \
  --namespace sub-00000001

# Output as table
itlc resource list-ips \
  --vnet prod-vnet \
  --subnet prod-subnet \
  -o table
```

**Output:**
```
IP ADDRESS    RESOURCE TYPE  RESOURCE NAME             NAMESPACE      POD NAME
10.0.1.5      pod            api-server-7d8f9c2a       sub-00000001   api-server-7d8f9c2a
10.0.1.10     pod            cache-worker-a3b2c1d0     sub-00000001   cache-worker-a3b2c1d0
10.0.1.15     pod            db-connector-f7e9d2c3     sub-00000001   db-connector-f7e9d2c3
```

---

## LoadBalancer Service IPs

```bash
# List all LoadBalancer IPs in a VNet
itlc resource list-lbs \
  --resource-type "virtualNetworks/loadBalancerIps" \
  --vnet prod-vnet

# List all LoadBalancer IPs across all VNets
itlc resource list-lbs

# Filter by tenant
itlc resource list-lbs \
  --vnet prod-vnet \
  --namespace sub-00000001

# Show only pending IPs
itlc resource list-lbs \
  --vnet prod-vnet \
  --filter "status=pending"

# Output as JSON
itlc resource list-lbs \
  --vnet prod-vnet \
  -o json
```

**Output (table format):**
```
IP ADDRESS    RESOURCE NAME      NAMESPACE      RESOURCE TYPE   STATUS   LAST SEEN
10.200.0.50   api-gateway-lb     sub-00000001   loadbalancer    active   2026-06-05T12:34:56Z
10.200.0.51   database-lb        sub-00000001   loadbalancer    active   2026-06-05T12:30:00Z
10.200.0.52   pending-service    sub-00000002   loadbalancer    pending  2026-06-05T12:35:01Z
```

---

## IPAM Capacity & Utilization

```bash
# Get IPAM data for a single subnet
itlc resource get-ipam \
  --vnet prod-vnet \
  --subnet prod-subnet

# Get IPAM data for entire VNet
itlc resource get-ipam \
  --vnet prod-vnet
```

**Output:**
```
VNET             SUBNET        CIDR            TOTAL IPs  USABLE IPs  ACTIVE  AVAILABLE  UTILIZATION
prod-vnet        prod-subnet   10.0.1.0/24     256        254         42      200        21.3%
```

---

**Last Updated:** June 2026
