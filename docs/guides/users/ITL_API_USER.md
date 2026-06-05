# For ITL ControlPlane API Users: Network Resource Management

How to use the ITL Network Provider API to manage network resources and expose applications with direct VLAN IP addresses.

---

## Overview

Within the ITL ControlPlane model:

- **You own a subscription** (e.g., `sub-00000001`)
- **You create VNets** within your subscription
- **You create Load Balancers & Application Gateways** via the ControlPlane API
- **Cilium automatically assigns VLAN IPs** from your cluster's BGP pool
- **Your services are routable directly from the physical network**

```
Your ITL Subscription (sub-00000001)
 VNet (prod-vnet: 10.0.0.0/16)
    Subnet (10.0.1.0/24)
 Load Balancer (my-api-lb)
    Gets VLAN IP: 10.200.0.50
 Application Gateway (my-gateway)
     Gets VLAN IP: 10.200.0.51

Physical Network (VLAN 100: 10.200.0.0/24)
 10.200.0.50 (my-api-lb)  Direct routing via BGP
 10.200.0.51 (my-gateway)  Direct routing via BGP
```

---

## Step 1: Create Your VNet via ITL API

### Using ITL CLI (itlc)

```bash
# Login to ITL ControlPlane
itlc login

# Set your subscription
itlc realm set --subscription sub-00000001

# Create VNet
itlc resource create \
  --resource-type virtualNetworks \
  --resource-name prod-vnet \
  --resource-group prod-rg \
  --location eastus \
  --properties '{
    "addressSpace": ["10.0.0.0/16"]
  }'

# Response:
# {
#   "id": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/prod-vnet",
#   "name": "prod-vnet",
#   "type": "Microsoft.Network/virtualNetworks",
#   "location": "eastus",
#   "properties": {
#     "addressSpace": ["10.0.0.0/16"],
#     "provisioningState": "Succeeded"
#   }
# }
```

### Using Direct REST API

```bash
# Get your auth token
TOKEN=$(itlc get-token)

# Create VNet
curl -X POST https://api.itlusions.com/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/prod-vnet \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "location": "eastus",
    "properties": {
      "addressSpace": ["10.0.0.0/16"]
    }
  }'
```

### Using PowerShell (itlc + Az)

```powershell
# Import ITL module
Import-Module itl-controlplane

# Create VNet
$vnet = New-ITLVirtualNetwork `
  -SubscriptionId "sub-00000001" `
  -ResourceGroupName "prod-rg" `
  -Name "prod-vnet" `
  -Location "eastus" `
  -AddressSpace "10.0.0.0/16"

$vnet.Id
# /subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/prod-vnet
```

---

## Step 2: Create Subnet

```bash
# CLI
itlc resource create \
  --resource-type "virtualNetworks/subnets" \
  --resource-name subnet-1 \
  --resource-group prod-rg \
  --parent-resource prod-vnet \
  --properties '{
    "addressPrefix": "10.0.1.0/24"
  }'

# Or REST
curl -X POST https://api.itlusions.com/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/prod-vnet/subnets/subnet-1 \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"properties": {"addressPrefix": "10.0.1.0/24"}}'
```

---

## Step 3: Create Load Balancer (Layer 4)

```bash
itlc resource create \
  --resource-type loadBalancers \
  --resource-name my-api-lb \
  --resource-group prod-rg \
  --location eastus \
  --properties '{
    "sku": {
      "name": "Standard"
    },
    "frontendIPConfigurations": [{
      "name": "frontend-ip",
      "properties": {
        "subnet": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/prod-vnet/subnets/subnet-1",
        "privateIPAllocationMethod": "Dynamic"
      }
    }],
    "backendAddressPools": [{
      "name": "backend-pool",
      "properties": {}
    }],
    "loadBalancingRules": [{
      "name": "http-rule",
      "properties": {
        "frontendIPConfiguration": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/loadBalancers/my-api-lb/frontendIPConfigurations/frontend-ip",
        "backendAddressPool": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/loadBalancers/my-api-lb/backendAddressPools/backend-pool",
        "protocol": "TCP",
        "frontendPort": 80,
        "backendPort": 8080,
        "enableFloatingIP": false,
        "idleTimeoutInMinutes": 4
      }
    }]
  }'

# Get the assigned VLAN IP
itlc resource get \
  --resource-type loadBalancers \
  --resource-name my-api-lb \
  --resource-group prod-rg
```

---

## Step 4: Create Application Gateway (Layer 7)

For more advanced routing with URL paths, hostnames, SSL/TLS:

```bash
itlc resource create \
  --resource-type applicationGateways \
  --resource-name my-gateway \
  --resource-group prod-rg \
  --location eastus \
  --properties '{
    "sku": {
      "name": "Standard_v2",
      "tier": "Standard_v2",
      "capacity": 2
    },
    "gatewayIPConfigurations": [{
      "name": "appGatewayIpConfig",
      "properties": {
        "subnet": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/prod-vnet/subnets/subnet-1"
      }
    }],
    "frontendPorts": [{
      "name": "port-80",
      "properties": {"port": 80}
    }],
    "backendAddressPools": [{
      "name": "backend-api",
      "properties": {
        "backendAddresses": [
          {"ipAddress": "10.0.1.10"},
          {"ipAddress": "10.0.1.11"}
        ]
      }
    }],
    "httpListeners": [{
      "name": "http-listener",
      "properties": {
        "frontendIPConfiguration": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/applicationGateways/my-gateway/frontendIPConfigurations/appGatewayFrontendIP",
        "frontendPort": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/applicationGateways/my-gateway/frontendPorts/port-80",
        "protocol": "Http"
      }
    }],
    "requestRoutingRules": [{
      "name": "routing-rule",
      "properties": {
        "ruleType": "Basic",
        "httpListener": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/applicationGateways/my-gateway/httpListeners/http-listener",
        "backendAddressPool": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/applicationGateways/my-gateway/backendAddressPools/backend-api",
        "backendHttpSettings": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/applicationGateways/my-gateway/backendHttpSettingsCollection/http-settings"
      }
    }],
    "backendHttpSettingsCollection": [{
      "name": "http-settings",
      "properties": {
        "port": 8080,
        "protocol": "Http",
        "cookieBasedAffinity": "Disabled"
      }
    }]
  }'

# Get the assigned VLAN IP (wait 30-60 seconds for Cilium to assign)
itlc resource get \
  --resource-type applicationGateways \
  --resource-name my-gateway \
  --resource-group prod-rg \
  --output json | jq '.properties.publicIPAddress'
```

---

## Step 5: Check Assigned VLAN IPs

```bash
# List all load balancers in your subscription
itlc resource list \
  --resource-type loadBalancers \
  --subscription sub-00000001 \
  --output table

# Output:
# NAME           RESOURCE_GROUP  VLAN_IP         PROVISIONING_STATE
# my-api-lb      prod-rg         10.200.0.50     Succeeded
# database-lb    prod-rg         10.200.0.51     Succeeded

# Get specific resource with full details
itlc resource get \
  --resource-type loadBalancers \
  --resource-name my-api-lb \
  --resource-group prod-rg \
  --output json
```

---

## Step 6: Access Your Service

```bash
# From anywhere on your physical network
curl http://10.200.0.50
#  Direct VLAN access!

# From inside cluster (using internal IP)
kubectl run debug --image=curlimages/curl -it -- curl http://my-api-lb.default.svc.cluster.local

# Port forwarding (for local development)
itlc port-forward \
  --resource-type loadBalancers \
  --resource-name my-api-lb \
  --resource-group prod-rg \
  --local-port 8080 \
  --remote-port 80

# Then: curl localhost:8080
```

---

## Real-World Scenario: Multi-Tier Application

### Create the infrastructure

```bash
# 1. VNet for production environment
itlc resource create \
  --resource-type virtualNetworks \
  --resource-name prod-vnet \
  --resource-group prod-rg \
  --properties '{"addressSpace": ["10.0.0.0/16"]}'

# 2. Frontend subnet
itlc resource create \
  --resource-type "virtualNetworks/subnets" \
  --resource-name frontend \
  --parent-resource prod-vnet \
  --resource-group prod-rg \
  --properties '{"addressPrefix": "10.0.1.0/24"}'

# 3. Backend subnet
itlc resource create \
  --resource-type "virtualNetworks/subnets" \
  --resource-name backend \
  --parent-resource prod-vnet \
  --resource-group prod-rg \
  --properties '{"addressPrefix": "10.0.2.0/24"}'

# 4. NSG for frontend (allow HTTP/HTTPS)
itlc resource create \
  --resource-type networkSecurityGroups \
  --resource-name frontend-nsg \
  --resource-group prod-rg \
  --properties '{
    "securityRules": [
      {
        "name": "allow-http",
        "properties": {
          "direction": "Inbound",
          "access": "Allow",
          "protocol": "TCP",
          "sourcePortRange": "*",
          "destinationPortRange": "80",
          "sourceAddressPrefix": "*",
          "destinationAddressPrefix": "*"
        }
      },
      {
        "name": "allow-https",
        "properties": {
          "direction": "Inbound",
          "access": "Allow",
          "protocol": "TCP",
          "sourcePortRange": "*",
          "destinationPortRange": "443",
          "sourceAddressPrefix": "*",
          "destinationAddressPrefix": "*"
        }
      }
    ]
  }'

# 5. Application Gateway (public endpoint)
itlc resource create \
  --resource-type applicationGateways \
  --resource-name public-gateway \
  --resource-group prod-rg \
  --properties '{
    "sku": {"name": "Standard_v2", "tier": "Standard_v2", "capacity": 2},
    "frontendPorts": [
      {"name": "port-80", "properties": {"port": 80}},
      {"name": "port-443", "properties": {"port": 443}}
    ],
    "httpListeners": [
      {
        "name": "http-listener",
        "properties": {"protocol": "Http", "port": 80}
      }
    ],
    "backendAddressPools": [
      {
        "name": "api-servers",
        "properties": {}
      }
    ]
  }'

# 6. Load Balancer (internal, for backend services)
itlc resource create \
  --resource-type loadBalancers \
  --resource-name internal-lb \
  --resource-group prod-rg \
  --properties '{
    "sku": {"name": "Standard"},
    "frontendIPConfigurations": [{
      "name": "internal-ip"
    }],
    "backendAddressPools": [{
      "name": "database-servers"
    }]
  }'
```

### Result

```bash
# Public endpoint (VLAN 100)
itlc resource get --resource-type applicationGateways --resource-name public-gateway
# VLAN IP: 10.200.0.100

# Internal endpoint (VLAN 100, but only routable from within network)
itlc resource get --resource-type loadBalancers --resource-name internal-lb
# VLAN IP: 10.200.0.101

# Access:
curl http://10.200.0.100           #  Public gateway
curl http://10.200.0.101           #  Internal LB (from authorized hosts)
```

---

## Multi-Subscription Scenario

### Subscription A (sub-00000001)

```bash
itlc realm set --subscription sub-00000001

# Create infrastructure
itlc resource create --resource-type virtualNetworks \
  --resource-name tenant-a-vnet \
  --properties '{"addressSpace": ["10.0.0.0/16"]}'

itlc resource create --resource-type loadBalancers \
  --resource-name tenant-a-api \
  --properties '{...}'

# Gets VLAN IP: 10.200.0.50 (from Storage cluster VLAN 100)
```

### Subscription B (sub-00000002)

```bash
itlc realm set --subscription sub-00000002

# Create infrastructure
itlc resource create --resource-type virtualNetworks \
  --resource-name tenant-b-vnet \
  --properties '{"addressSpace": ["10.0.0.0/16"]}'  # SAME CIDR, isolated!

itlc resource create --resource-type loadBalancers \
  --resource-name tenant-b-api \
  --properties '{...}'

# Gets VLAN IP: 10.200.0.60 (from Storage cluster VLAN 100)
```

### Network Isolation

```
Both subscriptions use 10.0.0.0/16  NO CONFLICT (Kubernetes namespace isolation)

Subscription A traffic: 10.200.0.50  Namespace sub-00000001  Isolated by Cilium policy
Subscription B traffic: 10.200.0.60  Namespace sub-00000002  Isolated by Cilium policy
```

---

## Cross-Cluster Resilience

Your subscription spans all 3 clusters:

```bash
# Storage cluster (VLAN 100)
itlc resource list --resource-type loadBalancers --subscription sub-00000001
# tenant-a-api:  10.200.0.50 (Storage)

# Data cluster (VLAN 200)
itlc resource list --resource-type loadBalancers --subscription sub-00000001 --cluster data-cluster
# tenant-a-api:  10.201.0.50 (Data)

# Compute cluster (VLAN 300)
itlc resource list --resource-type loadBalancers --subscription sub-00000001 --cluster compute-cluster
# tenant-a-api:  10.202.0.50 (Compute)

# All three are routable via BGP!
# Cluster failover? Traffic automatically redirects.
```

---

## Integration with Private Link

### Producer Exposes Service

```bash
# In subscription sub-producer
itlc resource create \
  --resource-type privateLinkServices \
  --resource-name database-service \
  --resource-group prod-rg \
  --properties '{
    "loadBalancerFrontendIPConfigurations": [{
      "id": "/subscriptions/sub-producer/resourceGroups/prod-rg/providers/Microsoft.Network/loadBalancers/db-lb/frontendIPConfigurations/config1"
    }],
    "networkInterfaceIPConfigurations": [{
      "name": "nic-config",
      "properties": {
        "primary": true,
        "privateIPAddress": "10.0.1.50",
        "privateIPAddressVersion": "IPv4"
      }
    }],
    "autoApprovalSubscriptions": ["sub-consumer"]
  }'
```

### Consumer Creates Private Endpoint

```bash
# In subscription sub-consumer
itlc resource create \
  --resource-type privateEndpoints \
  --resource-name database-endpoint \
  --resource-group prod-rg \
  --properties '{
    "privateLinkServiceConnections": [{
      "name": "db-connection",
      "properties": {
        "privateLinkServiceId": "/subscriptions/sub-producer/resourceGroups/prod-rg/providers/Microsoft.Network/privateLinkServices/database-service",
        "groupIds": ["database"]
      }
    }],
    "subnet": "/subscriptions/sub-consumer/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/vnet/subnets/endpoint-subnet"
  }'

# Gets private IP: 10.255.1.50 (not a VLAN IP, internal)
# But it routes through Cilium with cross-subscription policy
```

---

## Monitoring & Management

### Check Resource Status

```bash
# List all resources in your subscription
itlc resource list --subscription sub-00000001 --output table

# Monitor provisioning state
itlc resource get --resource-type applicationGateways --resource-name my-gateway --watch

# Get health status
itlc resource health --resource-type loadBalancers --resource-name my-api-lb

# Output:
# NAME        TYPE             STATUS      VLAN_IP         ENDPOINTS
# my-api-lb   LoadBalancer     Healthy     10.200.0.50     3/3 pods running
```

### Audit Trail

```bash
# View who created/modified resources
itlc resource audit --resource-type loadBalancers --resource-name my-api-lb

# Output shows:
# Created by: user@example.com at 2026-06-05 14:32:01
# Last modified by: user@example.com at 2026-06-05 15:15:22
# Operations: Create, Update, Update
```

### Metrics & Performance

```bash
# Get traffic statistics
itlc resource metrics \
  --resource-type loadBalancers \
  --resource-name my-api-lb \
  --metric "BytesProcessed" \
  --time-range "1h"

# Output:
# Timestamp          Bytes          Connections
# 2026-06-05 15:00   1.2 GB         45,000
# 2026-06-05 16:00   1.8 GB         62,000
```

---

## CLI Command Reference

### Resource Management

```bash
# Create
itlc resource create --resource-type loadBalancers --resource-name myresource ...

# List
itlc resource list --resource-type loadBalancers --subscription sub-001

# Get
itlc resource get --resource-type loadBalancers --resource-name myresource

# Update
itlc resource update --resource-type loadBalancers --resource-name myresource ...

# Delete
itlc resource delete --resource-type loadBalancers --resource-name myresource

# Watch (real-time updates)
itlc resource get --resource-type loadBalancers --resource-name myresource --watch
```

### Output Formats

```bash
# JSON (default)
itlc resource get ... --output json

# Table
itlc resource get ... --output table

# YAML
itlc resource get ... --output yaml

# Filtered JSON
itlc resource get ... --output json | jq '.properties.publicIPAddress'
```

### Common Filters

```bash
# By resource group
itlc resource list --resource-type loadBalancers --resource-group prod-rg

# By subscription
itlc resource list --resource-type loadBalancers --subscription sub-00000001

# By status
itlc resource list --resource-type loadBalancers --status Succeeded

# Combined
itlc resource list --resource-type loadBalancers \
  --subscription sub-00000001 \
  --resource-group prod-rg \
  --status Succeeded
```

---

## Troubleshooting via ITL API

### Resource Not Getting VLAN IP

```bash
# Check provisioning status
itlc resource get --resource-type loadBalancers --resource-name myresource

# If status is "Provisioning", wait 30-60 seconds
# If status is "Failed", check error:
itlc resource get --resource-type loadBalancers --resource-name myresource --show-errors

# Error messages indicate:
# - No IP pool available
# - Cilium not healthy
# - Namespace not created
```

### Access Denied

```bash
# Check your permissions in subscription
itlc whoami

# Check subscription access
itlc resource list --subscription sub-00000001

# If access denied, request from subscription owner or admin
```

### Cross-Cluster Issues

```bash
# Check which cluster resource is in
itlc resource get --resource-type loadBalancers --resource-name myresource --show-cluster

# Check cluster health
itlc cluster list

# If cluster down, failover to another:
itlc resource get --resource-type loadBalancers --resource-name myresource --cluster data-cluster
```

---

## Best Practices

### Best Practices:

#### DO:

- [x] Use descriptive resource names (`api-lb`, not `lb1`)
- [x] Organize by resource group (prod-rg, staging-rg)
- [x] Use multiple replicas for HA
- [x] Monitor resource health regularly
- [x] Keep track of VLAN IP allocations
- [x] Document your resources for your team

### [-] DON'T:

- [-] Share VLAN IPs across applications
- [-] Expose internal services without NSGs
- [-] Assume VLAN IPs are permanently static (recreate = new IP)
- [-] Forget to document backend configurations
- [-] Mix production and staging in same subnet

---

## Performance Expectations

| Operation | Time |
|---|---|
| Create VNet | 5-10 seconds |
| Create Subnet | 2-5 seconds |
| Create Load Balancer | 10-30 seconds |
| Assign VLAN IP | 15-45 seconds |
| BGP route advertisement | 2-5 seconds |
| First external request | < 1 second |

---

## Support & Help

**ITL ControlPlane Documentation:**
- `itlc --help`
- `itlc resource --help`
- `itlc realm --help`

**Network Documentation:**
- [../../operations/BGP_VLAN_SETUP.md](../../operations/BGP_VLAN_SETUP.md)  Infrastructure details
- [../../technical/ARCHITECTURE.md](../../technical/ARCHITECTURE.md)  How everything works
- [../TROUBLESHOOTING.md](../TROUBLESHOOTING.md)  Debug common issues

**Get Support:**
- Email: dev@itlusions.com
- Slack: #itl-network-support
- GitHub Issues: [ITL.ControlPlane.ResourceProvider.Network](https://github.com/ITlusions/ITL.ControlPlane.ResourceProvider.Network/issues)
