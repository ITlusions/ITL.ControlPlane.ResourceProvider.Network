# Network Isolation & Security

How Network Provider isolates workloads and enforces security policies.

---

## The Challenge

In a multi-tenant Kubernetes cluster, you need to ensure:

```
 Subscription A pods can't access Subscription B's data
 Subscription A can't sniff Subscription B's traffic
 Subscription A can't modify Subscription B's policies
 Subscription A can't see Subscription B's services

But:

 Within Subscription A, pods communicate freely
 Cross-subscription communication only when explicitly allowed (peering)
 Network policies enforced consistently across clusters
```

---

## Isolation Layers

### Layer 1: Kubernetes Namespace

Each subscription gets its own namespace:

```
Storage Cluster
 Namespace: sub-a
   Pods, Services, all resources isolated
 Namespace: sub-b
   Pods, Services, all resources isolated
 Namespace: kube-system
    Cilium, CoreDNS, system pods
```

**Isolation provided:**
- Service names scoped to namespace
- Pod-to-pod communication defaults to same namespace only
- Resource quotas enforced per namespace
- RBAC can restrict access per namespace

### Layer 2: Cilium Network Policy

Cilium enforces L3/L4 network policies at the Linux kernel level (eBPF):

```yaml
# Automatically created for NSGs
CiliumNetworkPolicy:
  metadata:
    name: nsg-frontend
    namespace: sub-a
  spec:
    endpointSelector:
      matchLabels:
        vnet: vnet-prod
    policyTypes:
      - Ingress
      - Egress
    ingress:
      - fromEndpoints:
          - matchLabels:
              vnet: vnet-prod
        toPorts:
          - ports:
              - port: "80"
                protocol: TCP
```

**Isolation provided:**
- L3/L4 traffic filtering
- Can't be bypassed (enforced at kernel)
- Per-pod level granularity
- Applied across all clusters

### Layer 3: Service Mesh (Cilium Service Mesh Optional)

For advanced use cases, enable Cilium service mesh for:
- Mutual TLS (mTLS) between pods
- Circuit breaking
- Rate limiting
- Advanced observability

---

## Network Security Group (NSG) to Cilium Translation

### NSG Rule

```json
{
  "name": "AllowHTTP",
  "properties": {
    "direction": "Inbound",
    "access": "Allow",
    "priority": 100,
    "protocol": "TCP",
    "sourcePortRange": "*",
    "destinationPortRange": "80",
    "sourceAddressPrefix": "10.0.0.0/24",
    "destinationAddressPrefix": "*"
  }
}
```

### Cilium Policy Translation

```yaml
CiliumNetworkPolicy:
  metadata:
    name: nsg-allow-http
    namespace: sub-001
  spec:
    endpointSelector:
      matchLabels:
        nsg: allow-http
    policyTypes:
      - Ingress
    ingress:
      - fromCIDRs:
          - 10.0.0.0/24
        toPorts:
          - ports:
              - port: "80"
                protocol: TCP
```

**Result:** Packets matching CIDR + port allowed, all others blocked by Cilium

---

## Multi-Subscription Isolation: Example

### Subscription A (Prod)

```yaml
Namespace: sub-prod
Resources:
 VNet: 10.0.0.0/16
 NSG: Allow 80/443 from internet, 5432 from app tier
 Pods:
    web-server (port 80)
    database (port 5432)

Security:
 Only web-server and database pods
 Web-server can receive traffic on 80
 Database only accepts from web-server on 5432
 No external access to database
 No pods from sub-staging can access
```

### Subscription B (Staging)

```yaml
Namespace: sub-staging
Resources:
 VNet: 10.1.0.0/16 (different CIDR)
 NSG: Allow 80 from anywhere
 Pods:
    web-server (port 80)
    debug-pod (all traffic for testing)

Security:
 Completely separate from sub-prod
 Can access databases within sub-staging
 Cannot access any sub-prod resources
 sub-prod cannot access this namespace
```

### Network Paths (Blocked)

```
sub-prod web-server (10.0.1.5)
     Can reach: Database (same namespace) 
     Can reach: sub-staging pods (NO - blocked by namespace isolation) 
     Result: Traffic blocked at Cilium

sub-staging debug-pod (10.1.1.10)
     Can reach: Web server (same namespace) 
     Can reach: sub-prod database (NO - blocked by Cilium policy) 
     Result: Traffic blocked at Cilium
```

---

## Cross-Subscription Communication: Peering

### Enabling Communication

To allow pods from sub-a to reach services in sub-b:

```bash
# 1. Create peering from sub-a  sub-b
itlc resource create --resource-type "virtualNetworks/virtualNetworkPeerings" \
  --resource-name app-to-db-peering \
  --properties '{
    "remoteVirtualNetwork": "/subscriptions/sub-b/...",
    "allowVirtualNetworkAccess": true
  }'
```

### Cilium Policy Created

**In sub-a namespace:**
```yaml
CiliumNetworkPolicy:
  name: peering-to-sub-b
  spec:
    egress:
      - toCIDRs:
          - 10.1.0.0/16  # sub-b CIDR
        toPorts:
          - ports:
              - port: "5432"
                protocol: TCP
```

**In sub-b namespace:**
```yaml
CiliumNetworkPolicy:
  name: peering-from-sub-a
  spec:
    ingress:
      - fromCIDRs:
          - 10.0.0.0/16  # sub-a CIDR
        toPorts:
          - ports:
              - port: "5432"
                protocol: TCP
```

### Result

```
sub-a pod (10.0.1.5)
     Tries to reach 10.1.1.10 (sub-b database)
     Cilium checks: "Is this allowed?"
     Policy found: Allow 10.0.0.0/16  10.1.0.0/16 on 5432
     Traffic ALLOWED 
```

---

## Private Link: Internal Service Exposure

### Scenario: Expose database service privately

```bash
# Create Private Link Service in sub-b
itlc resource create --resource-type privateLinkServices \
  --resource-name db-private-link \
  --properties '{
    "loadBalancerFrontendIPConfigurations": [...],
    "autoApprovalSubscriptions": ["sub-a"]
  }'

# Create Private Endpoint in sub-a
itlc resource create --resource-type privateEndpoints \
  --resource-name db-endpoint \
  --properties '{
    "privateLinkServiceConnections": [{
      "privateLinkServiceId": "/subscriptions/sub-b/.../db-private-link"
    }]
  }'
```

### Security

```
Private Link Service (sub-b)
   Only approved connections
Private Endpoint (sub-a)
   No internet access required
Result: Direct internal connection, no external IP exposure
```

---

## Traffic Encryption

### Without mTLS

```
sub-a pod (10.0.1.5)
     Unencrypted traffic to sub-b (10.1.1.10)
     Anyone on network can sniff data
     Not recommended for sensitive data
```

### With Cilium mTLS

```bash
# Enable service mesh
cilium install --helm-set serviceMesh.enabled=true
```

```
sub-a pod (10.0.1.5)
     TLS encrypted to sub-b (10.1.1.10)
     Automatic certificate management
     Perfect forward secrecy
     Encrypted end-to-end
```

---

## Audit & Compliance

### Network Policy Audit Logs

```bash
# View all policy changes
kubectl logs -n kube-system -l k8s-app=cilium --tail=100 | grep policy

# Or query database
SELECT * FROM audit_logs WHERE resource_type = 'networkSecurityGroups' ORDER BY timestamp DESC
```

### What's Logged

```
Timestamp: 2026-06-05T12:34:56Z
User: alice@itlusions.com
Action: Create
ResourceType: networkSecurityGroups
ResourceName: frontend-nsg
Subscription: sub-001
Details: {
  "securityRules": [...],
  "status": "Created"
}
```

### Compliance Reports

```bash
# NSGs created last 30 days
SELECT * FROM audit_logs 
WHERE resource_type = 'networkSecurityGroups'
AND timestamp > NOW() - INTERVAL '30 days'

# Peering changes
SELECT * FROM audit_logs
WHERE resource_type = 'virtualNetworkPeerings'
ORDER BY timestamp DESC
```

---

## Threat Model & Mitigations

### Threat 1: Pod Escape

**Threat:** Pod breaks out of namespace isolation

**Mitigation:**
- Cilium eBPF enforced in kernel (can't be bypassed from userspace)
- Pod sandbox restrictions
- Security context policies
- AppArmor/SELinux

### Threat 2: Network Eavesdropping

**Threat:** Attacker sniffs traffic between pods

**Mitigation:**
- mTLS encryption (Cilium service mesh)
- Network policy isolation reduces exposure surface
- Pod-to-pod traffic encrypted (optional)

### Threat 3: Policy Bypass

**Threat:** Attacker modifies network policies

**Mitigation:**
- RBAC prevents unauthorized policy changes
- Audit logs track all modifications
- Pod policies can't be changed from within pod
- Cilium policies immutable after creation

### Threat 4: DNS Spoofing

**Threat:** Attacker hijacks DNS to redirect traffic

**Mitigation:**
- CoreDNS DNSSEC validation (optional)
- Service discovery scoped to namespace
- Cilium identity-based routing (not IP-based)

---

## Best Practices

### Best Practices:

#### DO:

- [x] Use namespace isolation (always, one subscription per namespace)
- [x] Create explicit NSG rules (deny-by-default approach)
- [x] Enable mTLS for sensitive cross-subscription communication
- [x] Monitor Cilium policy logs regularly
- [x] Audit network changes
- [x] Test policies in staging before production

### [-] DON'T:

- [-] Assume namespaces are fully isolated (use Cilium policies too)
- [-] Leave "allow all" policies in production
- [-] Ignore audit logs
- [-] Use overlapping NSG names across subscriptions (confusing)
- [-] Create peering without business justification

---

## Troubleshooting

### Traffic blocked unexpectedly

```bash
# 1. Check Cilium policies
kubectl get ciliumnetworkpolicies -n {namespace}

# 2. Check specific policy
kubectl describe cnp {policy-name} -n {namespace}

# 3. Check Cilium flow logs
kubectl exec -it -n kube-system ds/cilium -- cilium monitor

# 4. Verify endpoint labels match policy selectors
kubectl get pods -n {namespace} -L vnet,nsg
```

### Cross-subscription communication failing

```bash
# 1. Verify peering exists
itlc resource get --resource-type virtualNetworkPeerings

# 2. Check policies in both namespaces
kubectl get ciliumnetworkpolicies -n sub-a | grep peering
kubectl get ciliumnetworkpolicies -n sub-b | grep peering

# 3. Test connectivity
kubectl exec pod-a -n sub-a -- ping pod-b.sub-b.svc.cluster.local
```

---

## Next Steps

- **Creating NSGs?**  [Manage NSGs](../tasks/MANAGE_NSGS.md)
- **Setting up peering?**  [Setup Peering](../tasks/SETUP_PEERING.md)
- **Need troubleshooting?**  [Troubleshooting](../reference/TROUBLESHOOTING.md)

---

**Last Updated:** June 2026
