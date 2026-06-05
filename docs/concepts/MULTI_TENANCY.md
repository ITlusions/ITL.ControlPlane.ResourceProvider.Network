# Multi-Tenancy & Subscription Model

How Network Provider isolates multiple subscriptions while supporting overlapping IP ranges.

---

## Core Principle: Namespace Isolation

Each subscription gets its own Kubernetes namespace. This provides:
- **Network isolation**  Pods can't communicate across namespaces without explicit policies
- **Policy enforcement**  NSGs apply only within the subscription
- **IP overlap safety**  Different subscriptions can use the same CIDR blocks
- **Multi-tenancy**  Complete separation of customer workloads

---

## Tenant vs Subscription Hierarchy

### Tenant = Keycloak Realm

A **tenant** is the top-level organization (Keycloak realm). Example:

```
Keycloak Realm: "itlusions.com"
   User: alice@itlusions.com (Roles: tenant-admin)
   User: bob@itlusions.com   (Roles: subscription-admin)
   User: charlie@itlusions.com (Roles: network-viewer)
```

### Subscription = Billing Container

A **subscription** is a billing/resource container within a tenant. Example:

```
Tenant: itlusions.com
 Subscription: sub-00000001 (Production)
   Owner: alice@itlusions.com
   Team: Platform engineers
   Resources: prod-vnet, prod-nsg, prod-lb

 Subscription: sub-00000002 (Staging)
   Owner: bob@itlusions.com
   Team: Dev team
   Resources: staging-vnet

 Subscription: sub-00000003 (Shared Services)
    Owner: alice@itlusions.com
    Resources: shared-registry, shared-logging
```

### Namespace Mapping

When you create a resource in a subscription, Network Provider:

1. **Maps subscription ID to namespace:**
   ```
   sub-00000001           Namespace: sub-00000001
   sub-ffffffff-...       Namespace: sub-ffffffff (first 8 chars)
   ```

2. **Creates namespace if needed:**
   ```bash
   kubectl create namespace sub-00000001
   kubectl label namespace sub-00000001 subscription=sub-00000001
   ```

3. **Applies network policies:**
   ```yaml
   CiliumNetworkPolicy:
     namespace: sub-00000001
     # Only pods in this namespace can access each other
   ```

---

## Overlapping IP Ranges: The Power of Namespaces

### The Problem (Without Namespace Isolation)

```
Subscription A wants: VNet 10.0.0.0/16
Subscription B wants: VNet 10.0.0.0/16   CONFLICT!

Traditional approach: Must use different CIDR per subscription
  Sub A: 10.0.0.0/16
  Sub B: 10.1.0.0/16
  Sub C: 10.2.0.0/16
  ...
   CIDR exhaustion!
```

### The Solution (Network Provider)

```
Subscription A  Namespace sub-a
   VNet: 10.0.0.0/16
   Pods: 10.0.1.0 - 10.0.254.0

Subscription B  Namespace sub-b
   VNet: 10.0.0.0/16 (same CIDR!)
   Pods: 10.0.1.0 - 10.0.254.0 (same range!)

NO CONFLICT because they're in separate namespaces!
```

### How It Works

Kubernetes handles IP allocation per namespace:

```
Storage Cluster (CIDR: 10.0.0.0/16)
 Namespace: sub-a
   Pod: 10.0.1.5 (only visible in this namespace)
   Pod: 10.0.1.6

 Namespace: sub-b
   Pod: 10.0.1.5 (same IP, different namespace - no conflict!)
   Pod: 10.0.1.6 (same IP, different namespace - no conflict!)

 Namespace: kube-system
    Pod: 10.0.254.1 (system pods)
```

DNS automatically scopes to namespaces:
```bash
# In pod from sub-a namespace
ping my-service                           # Resolves to sub-a instance
ping my-service.sub-b.svc.cluster.local  # Cross-namespace (requires policy)

# In pod from sub-b namespace
ping my-service                           # Resolves to sub-b instance
ping my-service.sub-a.svc.cluster.local  # Cross-namespace (requires policy)
```

---

## Multi-Subscription Peering

### Scenario: Two subscriptions need to communicate

**Subscription A (sub-a) wants to access database in Subscription B (sub-b).**

#### Step 1: Create VNets in each subscription

```bash
# Sub A: Create VNet
itlc realm set --subscription sub-a
itlc resource create --resource-type virtualNetworks \
  --resource-name app-vnet --properties '{"addressSpace": ["10.0.0.0/16"]}'

# Sub B: Create VNet
itlc realm set --subscription sub-b
itlc resource create --resource-type virtualNetworks \
  --resource-name db-vnet --properties '{"addressSpace": ["10.1.0.0/16"]}'
```

#### Step 2: Create peering

```bash
# From Sub A, peer to Sub B's VNet
itlc realm set --subscription sub-a
itlc resource create --resource-type "virtualNetworks/virtualNetworkPeerings" \
  --resource-name app-to-db \
  --parent-resource app-vnet \
  --properties '{
    "remoteVirtualNetwork": {
      "id": "/subscriptions/sub-b/resourceGroups/default/providers/Microsoft.Network/virtualNetworks/db-vnet"
    },
    "allowVirtualNetworkAccess": true
  }'
```

#### Step 3: Verify policies created

Network Provider creates Cilium policies in **both** namespaces:

```bash
# In sub-a namespace: allow outbound to sub-b
kubectl get ciliumnetworkpolicies -n sub-a
# OUTPUT: peering-to-sub-b (allows pods to reach 10.1.0.0/16)

# In sub-b namespace: allow inbound from sub-a
kubectl get ciliumnetworkpolicies -n sub-b
# OUTPUT: peering-from-sub-a (allows 10.0.0.0/16 to access services)
```

#### Step 4: Test connectivity

```bash
# Deploy app in sub-a
kubectl run app-pod -n sub-a --image=alpine -- sleep 3600

# Deploy db in sub-b
kubectl run db-pod -n sub-b --image=alpine -- sleep 3600

# Test from sub-a  sub-b
kubectl exec app-pod -n sub-a -- nslookup db-pod.sub-b.svc.cluster.local
# Should resolve and get 10.1.1.x IP

kubectl exec app-pod -n sub-a -- ping db-pod.sub-b.svc.cluster.local
# Should succeed! Cross-subscription communication works!
```

---

## Access Control

### Authentication: Keycloak OIDC

Every request includes a JWT token from Keycloak:

```bash
# Get token
TOKEN=$(itlc get-token)

# Use in API request
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8002/api/resource/...
```

Network Provider validates token and extracts:
- User ID
- Tenant (realm)
- Subscription assignments
- Roles (admin, writer, reader, auditor)

### Authorization: Role-Based Access Control (RBAC)

| Role | Permissions | Applied At |
|---|---|---|
| `itl-network-admin` | Full CRUD | Subscription |
| `itl-network-writer` | Create/update (no delete) | Subscription |
| `itl-network-reader` | Read-only | Subscription |
| `itl-network-auditor` | Audit logs only | Subscription |

### Subscription Assignment

Admin can assign roles per subscription:

```bash
# Admin assigns Alice to prod subscription as writer
itlc subscription assign \
  --subscription sub-prod \
  --user alice@itlusions.com \
  --role itl-network-writer

# Alice can now create resources in sub-prod
# But NOT in sub-staging (not assigned)
```

---

## Isolation in Action

### Example: Two Customers

#### Customer A: acme.com

```yaml
# Infrastructure
Tenant: acme.com (Keycloak realm)
Subscription: sub-acme-prod
Namespace: sub-acme-prod
VNet: 10.0.0.0/16
NSG: Allow 10.0.0.0/16 internally only

# Security
- No pods from other subscriptions can access
- Only users assigned to this subscription can create resources
- Audit logs track all changes
```

#### Customer B: widgets.corp

```yaml
# Infrastructure
Tenant: widgets.corp (Keycloak realm, different from acme!)
Subscription: sub-widgets-prod
Namespace: sub-widgets-prod
VNet: 10.0.0.0/16 (SAME CIDR as acme, no conflict!)
NSG: Allow 10.0.0.0/16 internally only

# Security
- Completely separate from acme.com
- Different Keycloak realm = no cross-access
- Even if both use 10.0.0.0/16, no conflict
```

### Network Isolation Verification

```bash
# Create test pods
kubectl run acme-pod -n sub-acme-prod --image=alpine -- sleep 3600
kubectl run widgets-pod -n sub-widgets-prod --image=alpine -- sleep 3600

# Try cross-namespace communication (should fail)
kubectl exec acme-pod -n sub-acme-prod -- ping widgets-pod.sub-widgets-prod.svc.cluster.local
# FAIL: No route to host (Cilium policy blocked it!)

# Create explicit peering to allow communication
# ... (requires admin approval and peering policy)
```

---

## Quota & Resource Limits

Network Provider enforces per-subscription limits:

```bash
# Default quotas (configurable)
Max VNets per subscription: 100
Max Subnets per VNet: 1000
Max NSG rules: 1000
Max Load Balancers: 50
Max IPs per VNet: 65536 (standard /16)
```

When quota exceeded:

```bash
# Try to create 101st VNet
itlc resource create --resource-type virtualNetworks ...
# ERROR: Subscription quota exceeded: 100/100 VNets already created
```

---

## Best Practices

### Best Practices:

#### DO:

- [x] Use one subscription per customer or environment (prod, staging, dev)
- [x] Assign roles carefully  only grant needed permissions
- [x] Audit logs regularly  track who changed what
- [x] Use consistent CIDR planning  even though overlap is safe, document your scheme
- [x] Test peering policies before production deployment

### [-] DON'T:

- [-] Share a subscription across unrelated teams
- [-] Assign global admin to everyone
- [-] Ignore audit logs
- [-] Create cross-subscription policies without business justification
- [-] Use overlapping CIDRs if you might need explicit routing later

---

## Troubleshooting Multi-Tenancy

### Pods can't communicate across subscriptions

**Symptom:** `ping service.other-sub.svc.cluster.local` fails

**Check:**
```bash
# Verify peering exists
itlc resource get --resource-type virtualNetworkPeerings ...

# Verify policy created
kubectl get ciliumnetworkpolicies -n {namespace}

# Check Cilium policy details
kubectl describe cnp peering-* -n {namespace}
```

### User can't create resources in subscription

**Symptom:** `Permission denied` error

**Check:**
```bash
# Verify user assignment
itlc subscription list --user alice@company.com

# Check roles
itlc whoami --show-roles

# Verify token includes subscription
itlc inspect-token # Check "sub" claim
```

### Namespace missing for subscription

**Symptom:** VNet creation fails with "namespace not found"

**Check:**
```bash
# List all subscription namespaces
kubectl get namespaces -L subscription

# If missing, recreate
kubectl create namespace {subscription-id}
kubectl label namespace {subscription-id} subscription={subscription-id}
```

---

## Next Steps

- **Creating your first VNet?**  [Create VNets](../tasks/CREATE_VNETS)
- **Setting up peering?**  [Setup Peering](../tasks/SETUP_PEERING)
- **Want API details?**  [API Reference](../reference/API_REFERENCE)

---

**Last Updated:** June 2026
