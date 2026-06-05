# Troubleshooting Guide

## Quick Reference

| Issue | Symptom | Likely Cause |
|---|---|---|
| Service won't start | Port 8002 connection refused | Docker not running, wrong port |
| Resource creation fails | HTTP 500 error | Kubernetes cluster unreachable or no auth |
| Kubernetes manifest missing | No pods in namespace | Namespace not created or permissions issue |
| DNS resolution fails | nslookup can't resolve service | CoreDNS not configured or zone not created |
| Network policy not working | Traffic not blocked by NSG | CiliumNetworkPolicy not created |

---

## Cluster Connectivity Issues

### Problem: "Cluster endpoint not reachable"

**Symptoms:**
- API requests fail with connection timeout
- Logs: `Failed to connect to storage cluster`
- Health check shows clusters as disconnected

**Diagnosis:**
```bash
# Test cluster endpoints manually
curl -k https://storage.cluster.local:6443/api/v1/namespaces
curl -k https://data.cluster.local:6443/api/v1/namespaces
curl -k https://compute.cluster.local:6443/api/v1/namespaces

# Check environment variables
echo $STORAGE_CLUSTER_ENDPOINT
echo $DATA_CLUSTER_ENDPOINT
echo $COMPUTE_CLUSTER_ENDPOINT
```

**Solutions:**

1. **Verify endpoints are correct:**
   ```bash
   # Check docker-compose
   cat docker-compose.yml | grep CLUSTER_ENDPOINT
   
   # Update if needed
   export STORAGE_CLUSTER_ENDPOINT=https://storage:6443
   export DATA_CLUSTER_ENDPOINT=https://data:6443
   export COMPUTE_CLUSTER_ENDPOINT=https://compute:6443
   ```

2. **Check network connectivity:**
   ```bash
   # From container
   docker-compose exec network-provider \
     curl -k https://storage:6443/api/v1/namespaces
   ```

3. **Verify KUBECONFIG:**
   ```bash
   # Ensure kubeconfig is mounted and valid
   docker-compose logs network-provider | grep kubeconfig
   
   # Check file exists
   ls -la /etc/kubernetes/kubeconfig
   ```

4. **Check K8s API server status:**
   ```bash
   # SSH to cluster
   ssh user@storage.cluster.local
   
   # Check API server
   kubectl get componentstatuses
   systemctl status kubelet
   ```

---

## Resource Creation Failures

### Problem: "409 Conflict - Resource already exists"

**Symptoms:**
- Create request returns 409 status
- Error message: `Resource already exists`
- Trying to recreate same resource fails

**Diagnosis:**
```bash
# Check if resource exists in cluster
kubectl get ciliumloadbalancerippools -n sub-00000001 | grep pool-a1b2c3d4
kubectl get ciliumnetworkpolicies -n sub-00000001 | grep nsg-frontend
```

**Solutions:**

1. **Resource is already created (expected):**
   ```bash
   # Just skip creation and proceed
   # Or delete first if you need to recreate
   curl -X DELETE ...
   ```

2. **Resource exists but hidden:**
   ```bash
   # List all resources
   kubectl get ciliumloadbalancerippools -A
   kubectl get ciliumnetworkpolicies -A
   
   # Delete if needed
   kubectl delete ciliumloadbalancerippools pool-a1b2c3d4 -n sub-00000001
   ```

3. **Database inconsistency:**
   ```bash
   # Check database
   docker-compose exec postgres psql -U controlplane -d controlplane
   
   SELECT * FROM virtual_networks WHERE name = 'vnet-prod';
   DELETE FROM virtual_networks WHERE name = 'vnet-prod';
   ```

---

### Problem: "404 Not Found - Resource doesn't exist"

**Symptoms:**
- Get/Update/Delete requests return 404
- Resource deletion fails with "already deleted"
- Trying to access non-existent resource

**Diagnosis:**
```bash
# Verify resource doesn't exist
curl http://localhost:8002/api/resource/subscriptions/sub-00000001/...

# Check K8s
kubectl get ciliumloadbalancerippools -n sub-00000001
```

**Solutions:**

1. **Resource was already deleted (expected):**
   ```bash
   # Idempotent delete is safe to retry
   curl -X DELETE ... 
   # Returns 404 (or 204 if found)
   ```

2. **Resource in wrong namespace:**
   ```bash
   # Check all namespaces
   kubectl get ciliumloadbalancerippools -A | grep pool-a1b2c3d4
   
   # Verify subscription mapping
   # sub-00000001  sub-00000001 namespace
   ```

3. **Database out of sync:**
   ```bash
   # Check database for orphaned records
   docker-compose exec postgres psql -U controlplane -d controlplane
   
   SELECT id, resource_id FROM virtual_networks WHERE resource_id NOT IN (
     SELECT resource_id FROM actual_resources
   );
   ```

---

## Network Connectivity Issues

### Problem: "Pods can't communicate across namespaces"

**Symptoms:**
- Peering created but pods still can't ping
- Policy exists but traffic blocked
- ClusterMesh not working

**Diagnosis:**
```bash
# Create test pods
kubectl run pod-a --image=alpine -n sub-00000001 -- sleep 3600
kubectl run pod-b --image=alpine -n sub-00000002 -- sleep 3600

# Try ping
kubectl exec -it pod-a -n sub-00000001 -- ping pod-b.sub-00000002.svc.cluster.local

# Check Cilium policies
kubectl get ciliumnetworkpolicies -n sub-00000001
kubectl describe cnp peer-* -n sub-00000001
```

**Solutions:**

1. **Peering not created:**
   ```bash
   # Verify peering exists
   curl http://localhost:8002/api/resource/.../virtualNetworkPeerings/peering-name
   
   # If missing, create it
   curl -X POST http://localhost:8002/api/resource ... -d '{ "properties": { "remoteVirtualNetwork": {...} } }'
   ```

2. **Policy has wrong selectors:**
   ```bash
   # Check policy details
   kubectl describe cnp peer-a1b2c3d4 -n sub-00000001
   
   # Verify selectors match namespace labels
   kubectl get namespaces -L "k8s:io.kubernetes.namespace"
   ```

3. **ClusterMesh not established:**
   ```bash
   # Check ClusterMesh status
   kubectl exec -it -n kube-system ds/cilium -- cilium clustermesh status
   
   # Should show all clusters connected
   # If not, check logs
   kubectl logs -n kube-system -l app=cilium -c cilium-agent | grep clustermesh
   ```

4. **DNS not resolving:**
   ```bash
   # Test DNS from pod
   kubectl exec -it pod-a -n sub-00000001 -- nslookup pod-b.sub-00000002.svc.cluster.local
   
   # Should return service IP
   # If not, check CoreDNS
   kubectl get svc -n kube-system | grep dns
   ```

---

### Problem: "Load balancer not receiving external traffic"

**Symptoms:**
- External IP assigned but unreachable
- Service created but no endpoint
- Traffic not reaching backend pods

**Diagnosis:**
```bash
# Check service
kubectl get svc -n sub-00000001 | grep lb-

# Check endpoints
kubectl get endpoints -n sub-00000001 | grep lb-

# Check Cilium pool
kubectl get ciliumloadbalancerippools -n kube-system | grep lb-

# Test connectivity
curl http://<external-ip>/
```

**Solutions:**

1. **Endpoints not assigned:**
   ```bash
   # Deploy backend pods
   kubectl run backend --image=nginx -n sub-00000001 --expose --port=80
   
   # Verify service picks up endpoints
   kubectl get endpoints -n sub-00000001
   ```

2. **External IP not allocated:**
   ```bash
   # Check Cilium pool has available IPs
   kubectl describe ciliumloadbalancerippools -n kube-system | grep Status
   
   # If exhausted, add more IPs to pool
   ```

3. **NSG blocking traffic:**
   ```bash
   # Check if NSG rule blocks port
   curl http://localhost:8002/api/resource/.../networkSecurityGroups/nsg-name
   
   # Verify allow rules for external traffic
   ```

---

## Multi-Cluster Issues

### Problem: "Resources not appearing in all clusters"

**Symptoms:**
- VNet created in storage cluster only
- Not replicated to data/compute clusters
- kubectl shows missing in some clusters

**Diagnosis:**
```bash
# Check storage cluster
kubectl --kubeconfig=$STORAGE_CONFIG get ciliumloadbalancerippools -n kube-system | grep pool-a1b2c3d4

# Check data cluster
kubectl --kubeconfig=$DATA_CONFIG get ciliumloadbalancerippools -n kube-system | grep pool-a1b2c3d4

# Check compute cluster
kubectl --kubeconfig=$COMPUTE_CONFIG get ciliumloadbalancerippools -n kube-system | grep pool-a1b2c3d4
```

**Solutions:**

1. **Some clusters unreachable:**
   ```bash
   # Check health
   curl http://localhost:8002/health
   
   # Should show all clusters connected
   # If not, verify endpoints and kubeconfig
   ```

2. **Creation failed silently:**
   ```bash
   # Check API logs for errors
   docker-compose logs network-provider | grep "Failed to create"
   
   # Try manual creation
   kubectl apply -f manifest.yaml
   ```

3. **Async deployment still pending:**
   ```bash
   # Multi-cluster deployment is parallel but may take time
   # Wait a few seconds and check again
   sleep 5
   kubectl --kubeconfig=$DATA_CONFIG get ciliumloadbalancerippools -n kube-system
   ```

---

## Database Issues

### Problem: "Database connection refused"

**Symptoms:**
- API fails to start: "connection refused"
- Logs: `psycopg2.OperationalError: could not connect to server`
- DATABASE_URL invalid

**Diagnosis:**
```bash
# Check if PostgreSQL is running
docker-compose ps | grep postgres

# Test connection
docker-compose exec network-provider \
  psql -h postgres -U controlplane -d controlplane -c "SELECT 1"
```

**Solutions:**

1. **PostgreSQL not running:**
   ```bash
   # Start PostgreSQL
   docker-compose up -d postgres
   
   # Wait for startup
   sleep 5
   ```

2. **DATABASE_URL incorrect:**
   ```bash
   # Check env
   docker-compose exec network-provider env | grep DATABASE_URL
   
   # Should be: postgresql://user:password@postgres:5432/controlplane
   # Update docker-compose.yml if needed
   ```

3. **Credentials wrong:**
   ```bash
   # Check docker-compose.yml
   grep -A5 "postgres:" docker-compose.yml
   
   # Verify POSTGRES_USER and POSTGRES_PASSWORD match DATABASE_URL
   ```

---

### Problem: "Audit logs not recording"

**Symptoms:**
- Operations succeed but logs not saved
- Audit queries return empty
- Unable to track resource changes

**Diagnosis:**
```bash
# Connect to database
docker-compose exec postgres psql -U controlplane -d controlplane

# Check audit_logs table
SELECT COUNT(*) FROM audit_logs;

# Check for errors
SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 5;
```

**Solutions:**

1. **Audit logging disabled:**
   ```bash
   # Check configuration
   echo $LOG_LEVEL
   
   # Set to INFO for logging
   export LOG_LEVEL=INFO
   docker-compose restart network-provider
   ```

2. **Table doesn't exist:**
   ```bash
   # Run migrations
   docker-compose exec network-provider alembic upgrade head
   ```

---

## Kubernetes Issues

### Problem: "CRD not found"

**Symptoms:**
- Error: "no matches for kind CiliumLoadBalancerIPPool"
- Cilium resources not recognized
- Custom resource creation fails

**Diagnosis:**
```bash
# Check if Cilium CRDs installed
kubectl get crd | grep cilium

# List all CRDs
kubectl get crd | grep cilium.io
```

**Solutions:**

1. **Cilium not installed:**
   ```bash
   # Install Cilium helm chart
   helm repo add cilium https://helm.cilium.io
   helm install cilium cilium/cilium \
     --namespace kube-system \
     --set clustermesh.enabled=true
   
   # Wait for cilium pods
   kubectl wait --for=condition=ready pod \
     -l k8s-app=cilium \
     -n kube-system \
     --timeout=300s
   ```

2. **Old Cilium version:**
   ```bash
   # Check version
   kubectl exec -it -n kube-system ds/cilium -- cilium version
   
   # Upgrade if needed
   helm upgrade cilium cilium/cilium ...
   ```

---

### Problem: "Namespace creation fails"

**Symptoms:**
- Error: "namespaces 'sub-00000001' already exists"
- Or: "Failed to create namespace"
- Namespace stuck in terminating state

**Diagnosis:**
```bash
# Check namespace status
kubectl get namespaces | grep sub-

# Check for stuck resources
kubectl get all -n sub-00000001

# Check events
kubectl describe ns sub-00000001
```

**Solutions:**

1. **Namespace already exists:**
   ```bash
   # This is expected for re-creating resources
   # Network Provider handles this with PATCH (idempotent)
   ```

2. **Namespace stuck terminating:**
   ```bash
   # Force delete namespace finalizers
   kubectl patch ns sub-00000001 -p '{"metadata":{"finalizers":null}}'
   
   # Or recreate
   kubectl delete ns sub-00000001 --force
   ```

---

## Authentication Issues

### Problem: "Unauthorized - invalid token"

**Symptoms:**
- 401 Unauthorized responses
- "Token validation failed"
- Missing Authorization header

**Diagnosis:**
```bash
# Check token
echo $TOKEN

# Verify token format
echo $TOKEN | cut -d. -f1 | base64 -d | jq .

# Check token expiry
echo $TOKEN | cut -d. -f2 | base64 -d | jq '.exp'
```

**Solutions:**

1. **Token expired:**
   ```bash
   # Get new token from Keycloak
   curl -X POST https://sts.itlusions.com/realms/itlusions/protocol/openid-connect/token \
     -d "grant_type=client_credentials" \
     -d "client_id=itl-network-provider" \
     -d "client_secret=YOUR_SECRET"
   
   # Save new token
   export TOKEN="new-jwt-token"
   ```

2. **Token format invalid:**
   ```bash
   # Should be "Bearer <token>"
   curl -H "Authorization: Bearer $TOKEN" ...
   
   # NOT: -H "Authorization: $TOKEN" ...
   ```

3. **Keycloak unreachable:**
   ```bash
   # Check Keycloak URL
   echo $KEYCLOAK_URL
   
   # Test connectivity
   curl https://sts.itlusions.com/.well-known/openid-configuration
   ```

---

## Performance Issues

### Problem: "Slow resource creation"

**Symptoms:**
- VNet creation takes >10 seconds
- Timeouts on large batch operations
- Multi-cluster deployment slow

**Diagnosis:**
```bash
# Check API response time
time curl -X POST http://localhost:8002/api/resource ... \
  -d '{ "properties": {...} }'

# Monitor cluster API latency
kubectl top nodes
kubectl top pods -n sub-00000001

# Check network latency
ping storage.cluster.local
ping data.cluster.local
ping compute.cluster.local
```

**Solutions:**

1. **Slow K8s API responses:**
   ```bash
   # Check API server logs
   kubectl logs -n kube-apiserver-pod ... -c kube-apiserver | tail -20
   
   # Check etcd performance
   kubectl exec -it etcd-pod -n kube-system -- etcdctl endpoint health
   ```

2. **Slow network between clusters:**
   ```bash
   # Measure latency
   ping -c 5 data.cluster.local
   ping -c 5 compute.cluster.local
   
   # If high (>100ms), check network path
   traceroute storage.cluster.local
   ```

3. **Resource limits hit:**
   ```bash
   # Check provider container resources
   docker stats network-provider
   
   # Increase if needed
   # Edit docker-compose.yml:
   # deploy:
   #   resources:
   #     limits:
   #       memory: 2G
   #       cpus: '1'
   ```

---

## Debugging Strategies

### Enable Debug Logging

```bash
# Set log level
export LOG_LEVEL=DEBUG

# Restart service
docker-compose restart network-provider

# View logs
docker-compose logs -f network-provider
```

### Check Health Endpoint

```bash
curl http://localhost:8002/health | jq .

# Expected output:
# {
#   "status": "healthy",
#   "clusters": {
#     "storage": "connected",
#     "data": "connected",
#     "compute": "connected"
#   },
#   "database": "connected",
#   "version": "0.1.0"
# }
```

### Query Database Directly

```bash
docker-compose exec postgres psql -U controlplane -d controlplane

# List all VNets
SELECT id, name, subscription_id, created_at FROM virtual_networks;

# List all NSGs
SELECT id, name, subscription_id FROM network_security_groups;

# Check audit log
SELECT operation, resource_id, user, timestamp FROM audit_logs ORDER BY timestamp DESC LIMIT 10;
```

### Monitor K8s Resources

```bash
# Watch Cilium pools
kubectl get ciliumloadbalancerippools -A -w

# Watch policies
kubectl get ciliumnetworkpolicies -A -w

# Watch BGP policies
kubectl get ciliumbgppeeringpolicies -A -w

# Watch services
kubectl get svc -A -w
```

---

**Last Updated:** June 2026
