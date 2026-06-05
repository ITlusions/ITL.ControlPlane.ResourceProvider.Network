# IP Address Management (IPAM) Guide

Complete reference for listing, discovering, and managing IPs in ITL Network Provider. Covers internal VNet IPs, external VLAN IPs, IPAM capacity planning, and real-time ARP discovery.

---

## 1. Active Pod IPs in Subnets

List all currently allocated pod IPs within a subnet.

### REST API

```bash
GET /api/v1/vnets/{vnet_name}/subnets/{subnet_name}/active-ips?namespace=sub-00000001
```

### Examples

**Get all active IPs in prod-subnet:**
```bash
curl http://localhost:8002/api/v1/vnets/prod-vnet/subnets/prod-subnet/active-ips
```

**Filter by namespace (subscription):**
```bash
curl http://localhost:8002/api/v1/vnets/prod-vnet/subnets/prod-subnet/active-ips?namespace=sub-00000001
```

### Response

```json
{
  "subnet": "prod-subnet",
  "vnet": "prod-vnet",
  "active_ips": [
    {
      "ip_address": "10.0.1.5",
      "subnet_cidr": "10.0.1.0/24",
      "resource_type": "pod",
      "resource_name": "api-server-7d8f9c2a",
      "namespace": "sub-00000001",
      "pod_name": "api-server-7d8f9c2a",
      "node_name": "node-1",
      "status": "active",
      "last_seen": "2026-06-05T12:34:56.789Z"
    }
  ],
  "total_count": 42
}
```

### Use Cases

- **Debugging connectivity**: Find which pods are using which IPs
- **Capacity planning**: See actual IP utilization
- **Network troubleshooting**: Identify pods in specific subnets
- **Security audits**: Track resource locations by IP

---

## 2. LoadBalancer Service IPs (VLAN IPs)

List all external VLAN IPs assigned to LoadBalancer services.

### REST API

```bash
GET /api/v1/vnets/{vnet_name}/loadbalancer-ips?namespace=sub-00000001
```

### Response

```json
{
  "vnet": "prod-vnet",
  "loadbalancer_ips": [
    {
      "ip_address": "10.200.0.50",
      "resource_type": "loadbalancer",
      "resource_name": "api-gateway-lb",
      "namespace": "sub-00000001",
      "status": "active",
      "last_seen": "2026-06-05T12:34:56.789Z"
    }
  ],
  "total_count": 8,
  "active_count": 7
}
```

---

## 3. IPAM Capacity Planning

Get subnet capacity, utilization, and IP reservation data.

### Subnet IPAM Response

```json
{
  "subnet": "prod-subnet",
  "vnet": "prod-vnet",
  "subnet_cidr": "10.0.1.0/24",
  "total_ips": 256,
  "usable_ips": 254,
  "active_ips": 42,
  "reserved_ips": 12,
  "available_ips": 200,
  "utilization_percent": 21.3
}
```

---

**Last Updated:** June 2026
