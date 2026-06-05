# Getting Started

## Prerequisites

- Docker & Docker Compose
- Kubernetes cluster(s) running Talos + Cilium
- PostgreSQL (provided in docker-compose)
- Python 3.11+ (for local development)
- `kubectl` CLI installed
- Keycloak for authentication

## Quick Start (Local Development)

### 1. Start Services

```bash
cd ITL.ControlPlane.ResourceProvider.Network
docker-compose up -d
```

This starts:
- Network Provider API (port 8002)
- PostgreSQL (port 5432)
- Redis (optional, for caching)

Verify services are running:
```bash
docker-compose ps
```

### 2. Verify Health

```bash
curl http://localhost:8002/health

# Expected response (200 OK):
# {
#     "status": "healthy",
#     "service": "itl-network-provider"
# }
```

### 3. Get Authentication Token

```bash
# Get token from Keycloak
curl -X POST https://sts.itlusions.com/realms/itlusions/protocol/openid-connect/token \
  -d "grant_type=client_credentials" \
  -d "client_id=itl-network-provider" \
  -d "client_secret=YOUR_SECRET" \
  -H "Content-Type: application/x-www-form-urlencoded"

# Save token
export TOKEN="eyJhbGc..."
```

---

## Creating Your First Virtual Network

### 1. Create a VNet

```bash
curl -X POST http://localhost:8002/api/resource \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptionId": "sub-00000001",
    "resourceGroup": "prod-rg",
    "resourceType": "virtualNetworks",
    "resourceName": "vnet-prod",
    "location": "eastus",
    "properties": {
      "addressSpace": ["10.0.0.0/16"]
    }
  }'
```

**Expected Response (201 Created):**
```json
{
    "id": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/vnet-prod",
    "name": "vnet-prod",
    "type": "Microsoft.Network/virtualNetworks",
    "location": "eastus",
    "properties": {
        "addressSpace": ["10.0.0.0/16"],
        "provisioningState": "Succeeded"
    }
}
```

### 2. Verify in Kubernetes

```bash
# Check Cilium pool created in storage cluster
kubectl get ciliumloadbalancerippools -n kube-system

# Check tenant namespace created
kubectl get namespaces | grep sub-

# Verify pool in subscription namespace
kubectl get ciliumloadbalancerippools -n sub-00000001
```

---

## Creating Subnets

### 1. Create First Subnet

```bash
curl -X POST http://localhost:8002/api/resource \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptionId": "sub-00000001",
    "resourceGroup": "prod-rg",
    "resourceType": "virtualNetworks/subnets",
    "resourceName": "subnet-frontend",
    "properties": {
      "addressPrefix": "10.0.1.0/24",
      "virtualNetworkId": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/vnet-prod"
    }
  }'
```

### 2. Create Second Subnet

```bash
curl -X POST http://localhost:8002/api/resource \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptionId": "sub-00000001",
    "resourceGroup": "prod-rg",
    "resourceType": "virtualNetworks/subnets",
    "resourceName": "subnet-backend",
    "properties": {
      "addressPrefix": "10.0.2.0/24",
      "virtualNetworkId": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/vnet-prod"
    }
  }'
```

---

## Network Security Groups (NSGs)

### 1. Create NSG with Rules

```bash
curl -X POST http://localhost:8002/api/resource \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptionId": "sub-00000001",
    "resourceGroup": "prod-rg",
    "resourceType": "networkSecurityGroups",
    "resourceName": "nsg-frontend",
    "location": "eastus",
    "properties": {
      "securityRules": [
        {
          "name": "allow-http",
          "properties": {
            "access": "Allow",
            "direction": "Inbound",
            "priority": 100,
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
            "access": "Allow",
            "direction": "Inbound",
            "priority": 110,
            "protocol": "TCP",
            "sourcePortRange": "*",
            "destinationPortRange": "443",
            "sourceAddressPrefix": "*",
            "destinationAddressPrefix": "*"
          }
        }
      ]
    }
  }'
```

### 2. Verify NSG in Cluster

```bash
# Check Cilium policy created
kubectl get ciliumnetworkpolicies -n sub-00000001

# View policy details
kubectl describe ciliumnetworkpolicies nsg-frontend -n sub-00000001
```

---

## Multi-Tenant Example

### Scenario: Two Subscriptions with Same CIDR

**Subscription A (sub-00000001):**
```bash
curl -X POST http://localhost:8002/api/resource \
  -H "Authorization: Bearer $TOKEN_SUB_A" \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptionId": "sub-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "resourceGroup": "rg-a",
    "resourceType": "virtualNetworks",
    "resourceName": "vnet-prod",
    "properties": {
      "addressSpace": ["10.0.0.0/16"]
    }
  }'
```

**Subscription B (sub-00000002)  Same CIDR!**
```bash
curl -X POST http://localhost:8002/api/resource \
  -H "Authorization: Bearer $TOKEN_SUB_B" \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptionId": "sub-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "resourceGroup": "rg-b",
    "resourceType": "virtualNetworks",
    "resourceName": "vnet-prod",
    "properties": {
      "addressSpace": ["10.0.0.0/16"]
    }
  }'
```

[x] **Both VNets created successfully!** They're isolated in separate Kubernetes namespaces:
- Subscription A  `sub-aaaaaaaa`
- Subscription B  `sub-bbbbbbbb`

---

## VNet Peering

### 1. Create Peering Between Subscriptions

Allow Subscription A and Subscription B to communicate:

```bash
curl -X POST http://localhost:8002/api/resource \
  -H "Authorization: Bearer $TOKEN_SUB_A" \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptionId": "sub-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "resourceGroup": "rg-a",
    "resourceType": "virtualNetworks/virtualNetworkPeerings",
    "resourceName": "peering-to-b",
    "properties": {
      "remoteVirtualNetwork": {
        "id": "/subscriptions/sub-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/resourceGroups/rg-b/providers/Microsoft.Network/virtualNetworks/vnet-prod"
      },
      "allowVirtualNetworkAccess": true,
      "allowForwardedTraffic": true,
      "allowGatewayTransit": false
    }
  }'
```

### 2. Verify Peering Policies

```bash
# Check policy in Subscription A namespace
kubectl get ciliumnetworkpolicies -n sub-aaaaaaaa

# Test connectivity between namespaces
kubectl run test-pod-a --image=alpine -n sub-aaaaaaaa -- sleep 3600
kubectl run test-pod-b --image=alpine -n sub-bbbbbbbb -- sleep 3600

# Try to ping from A to B
kubectl exec -it test-pod-a -n sub-aaaaaaaa -- ping test-pod-b.sub-bbbbbbbb.svc.cluster.local
```

---

## Load Balancer Creation

### Create External Load Balancer

```bash
curl -X POST http://localhost:8002/api/resource \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptionId": "sub-00000001",
    "resourceGroup": "prod-rg",
    "resourceType": "loadBalancers",
    "resourceName": "lb-web",
    "location": "eastus",
    "properties": {
      "sku": {
        "name": "Standard"
      }
    }
  }'
```

---

## Environment Variables

Create `.env` file or set in docker-compose:

```env
# Cluster endpoints
STORAGE_CLUSTER_ENDPOINT=https://storage.cluster.local:6443
DATA_CLUSTER_ENDPOINT=https://data.cluster.local:6443
COMPUTE_CLUSTER_ENDPOINT=https://compute.cluster.local:6443

# Kubernetes config
KUBECONFIG=/etc/kubernetes/kubeconfig

# Database
DATABASE_URL=postgresql://user:password@postgres:5432/controlplane

# Cilium
CILIUM_NAMESPACE=kube-system

# API
API_PORT=8002
LOG_LEVEL=INFO

# Authentication
KEYCLOAK_URL=https://sts.itlusions.com
KEYCLOAK_REALM=itlusions

# Resource limits
MAX_VNETS_PER_SUBSCRIPTION=100
MAX_SUBNETS_PER_VNET=1000
MAX_NSG_RULES=1000
```

---

## Testing Multi-Cluster Deployment

### 1. Create VNet and Verify Across Clusters

```bash
# Create VNet
curl -X POST http://localhost:8002/api/resource \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subscriptionId": "sub-00000001",
    "resourceGroup": "test-rg",
    "resourceType": "virtualNetworks",
    "resourceName": "vnet-multicluster",
    "properties": {
      "addressSpace": ["10.0.0.0/16"]
    }
  }'

# Check storage cluster
export STORAGE_KUBECONFIG=/path/to/storage-kubeconfig.yaml
kubectl --kubeconfig=$STORAGE_KUBECONFIG get ciliumloadbalancerippools -n kube-system | grep pool-

# Check data cluster
export DATA_KUBECONFIG=/path/to/data-kubeconfig.yaml
kubectl --kubeconfig=$DATA_KUBECONFIG get ciliumloadbalancerippools -n kube-system | grep pool-

# Check compute cluster
export COMPUTE_KUBECONFIG=/path/to/compute-kubeconfig.yaml
kubectl --kubeconfig=$COMPUTE_KUBECONFIG get ciliumloadbalancerippools -n kube-system | grep pool-
```

[x] **VNet should appear in all three clusters!**

### 2. Test Pod Connectivity Across Clusters

Deploy test pods in each cluster's subscription namespace:

```bash
# Storage cluster
kubectl --kubeconfig=$STORAGE_KUBECONFIG run test-storage --image=alpine -n sub-00000001 -- sleep 3600

# Data cluster
kubectl --kubeconfig=$DATA_KUBECONFIG run test-data --image=alpine -n sub-00000001 -- sleep 3600

# Compute cluster
kubectl --kubeconfig=$COMPUTE_KUBECONFIG run test-compute --image=alpine -n sub-00000001 -- sleep 3600

# Test connectivity from compute to storage
kubectl --kubeconfig=$COMPUTE_KUBECONFIG exec -it test-compute -n sub-00000001 -- \
  ping test-storage.sub-00000001.svc.cluster.local
```

---

## Debugging

### Check Provider Logs

```bash
docker-compose logs -f network-provider
```

### Check K8s Cluster Health

```bash
# Verify cluster connectivity
curl -k https://STORAGE_CLUSTER_ENDPOINT/api/v1/namespaces

# Check Cilium status
kubectl exec -it -n kube-system ds/cilium -- cilium status

# List all pools
kubectl get ciliumloadbalancerippools -A
```

### Query Database

```bash
docker-compose exec postgres psql -U controlplane -d controlplane

# List VNets
SELECT id, name, subscription_id, properties FROM virtual_networks;

# List NSGs
SELECT id, name, subscription_id, rules FROM network_security_groups;

# View audit logs
SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 10;
```

---

## Troubleshooting

### Resource Creation Fails with 409 Conflict

**Cause:** Resource already exists with same name.

**Solution:**
```bash
# Delete existing resource
curl -X DELETE http://localhost:8002/api/resource/... \
  -H "Authorization: Bearer $TOKEN"

# Recreate
```

### Clusters Not Connected

**Cause:** KUBECONFIG or cluster endpoints invalid.

**Solution:**
```bash
# Verify endpoints are reachable
curl -k https://STORAGE_CLUSTER_ENDPOINT/healthz
curl -k https://DATA_CLUSTER_ENDPOINT/healthz
curl -k https://COMPUTE_CLUSTER_ENDPOINT/healthz

# Check Health endpoint
curl http://localhost:8002/health
```

### Peering Not Working

**Cause:** CiliumNetworkPolicy not deployed correctly.

**Solution:**
```bash
# Verify policies exist in both namespaces
kubectl get ciliumnetworkpolicies -n sub-aaaaaaaa
kubectl get ciliumnetworkpolicies -n sub-bbbbbbbb

# Check policy details
kubectl describe cnp peer-* -n sub-aaaaaaaa

# Verify ClusterMesh status
kubectl exec -it -n kube-system ds/cilium -- cilium clustermesh status
```

---

## Next Steps

- Read [../technical/ARCHITECTURE.md](../technical/ARCHITECTURE.md) for design details
- Review [../technical/API_REFERENCE.md](../technical/API_REFERENCE.md) for all endpoints
- Explore [../operations/EXAMPLES.md](../operations/EXAMPLES.md) for advanced patterns
- Check troubleshooting in [../guides/TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

**Last Updated:** June 2026
