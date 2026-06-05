# Guide for Platform Operators

Running and maintaining Network Provider in production.

---

## Daily Operations

### Morning Checklist

```bash
# 1. Check health dashboard
curl http://localhost:8002/health

# 2. Review overnight alerts
# (from your monitoring system: Prometheus, DataDog, etc.)

# 3. Check all clusters connected
curl http://localhost:8002/health | jq '.clusters'

# 4. Database backup status
kubectl logs -n itl-network job/backup-database | tail -20
```

### Common Tasks

#### Adding a New Subscription

```bash
# 1. Create tenant/subscription in Control Plane
itlc subscription create \
  --subscription sub-customer-001 \
  --tenant customer.com \
  --owner alice@customer.com

# 2. Network Provider automatically creates namespace
# Verify:
kubectl get namespace sub-customer-001
kubectl get labels namespace sub-customer-001

# 3. Initialize quota
curl -X POST http://localhost:8002/subscriptions/sub-customer-001/quota \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "maxVnets": 100,
    "maxNsgs": 1000,
    "maxLoadBalancers": 50
  }'

# 4. Notify customer
# → They can now create VNets via REST API
```

#### Monitoring Resource Usage

```bash
# VNets per subscription
curl http://localhost:8002/subscriptions \
  -H "Authorization: Bearer $ADMIN_TOKEN" | \
  jq '.[] | {subscription: .id, vnets: (.resources | length)}'

# Quota utilization
curl http://localhost:8002/subscriptions/sub-001/quota \
  -H "Authorization: Bearer $ADMIN_TOKEN" | \
  jq '.usage'

# IP pool utilization per cluster
for CLUSTER in storage data compute; do
  kubectl --kubeconfig=~/.kube/$CLUSTER get ciliumloadbalancerippools -A \
    -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.status.available}{"\t"}{.status.total}{"\n"}{end}' | \
    awk '{total+=$3; available+=$2} END {print "'$CLUSTER': "available"/"total" IPs"}'
done
```

### Performance Optimization

#### Query Slow Resources

```sql
-- Find slowest API operations
SELECT operation, avg(duration_ms) as avg_duration, count(*) as count
FROM audit_logs
WHERE operation IN ('Create', 'Update', 'Delete')
GROUP BY operation
ORDER BY avg_duration DESC
LIMIT 10;

-- Find subscriptions with most resources
SELECT subscription_id, count(*) as resource_count
FROM resources
GROUP BY subscription_id
ORDER BY resource_count DESC
LIMIT 10;
```

#### Optimize Database

```bash
# Run maintenance
psql network_provider -c "ANALYZE;"  # Update statistics
psql network_provider -c "VACUUM;"   # Clean up bloat

# Check index usage
psql network_provider -c "
  SELECT schemaname, tablename, indexname
  FROM pg_indexes
  WHERE idx_scan = 0
  LIMIT 10;"

# Rebuild slow index
REINDEX INDEX CONCURRENTLY idx_resources_subscription;
```

---

## Troubleshooting & Incident Response

### Cluster Connectivity Issues

**Symptom:** One cluster shows "unreachable"

```bash
# 1. Check cluster connectivity
kubectl --kubeconfig=~/.kube/storage cluster-info

# 2. Verify API endpoint is reachable
curl -k https://api.storage.cluster:6443/healthz

# 3. Test kubeconfig
kubectl --kubeconfig=~/.kube/storage auth can-i get pods

# 4. Check Network Provider logs
kubectl logs -f deployment/network-provider -n itl-network

# 5. If kubeconfig wrong, update secret
kubectl create secret generic cluster-credentials \
  --from-literal=storage-kubeconfig=$(cat /tmp/storage-kubeconfig) \
  --dry-run=client -o yaml | \
  kubectl patch -f - --type merge -p '{"metadata":{"name":"cluster-credentials"}}' \
  -n itl-network
```

### High Latency

**Symptom:** API requests taking > 1 second

```bash
# 1. Check cluster latencies
for CLUSTER in storage data compute; do
  echo "Testing $CLUSTER..."
  kubectl --kubeconfig=~/.kube/$CLUSTER get nodes --no-headers | head -1
  time curl -s https://$(kubectl --kubeconfig=~/.kube/$CLUSTER cluster-info | grep 'Kubernetes master' | grep -oP 'https://\K[^ ]+'):6443/healthz >/dev/null
done

# 2. Check database latency
psql network_provider -c "SELECT 1;" | time
# Should be < 50ms

# 3. Check Pod logs for slow operations
kubectl logs deployment/network-provider -n itl-network | grep "duration_ms"

# 4. Check CPU/Memory usage
kubectl top pod -n itl-network --containers
# If high, scale up
kubectl scale deployment/network-provider --replicas=5 -n itl-network
```

### Resource Quota Exceeded

**Symptom:** User can't create new resources

```bash
# 1. Check current quota
curl http://localhost:8002/subscriptions/sub-001/quota \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.usage'

# 2. Increase quota
curl -X PUT http://localhost:8002/subscriptions/sub-001/quota \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "maxVnets": 200  # Increased from 100
  }'

# 3. Notify user
# "Quota increased, you can now create more resources"

# 4. Monitor (might indicate user error or misuse)
SELECT * FROM resources 
WHERE subscription_id = 'sub-001' 
ORDER BY created_at DESC LIMIT 10;
```

---

## Monitoring & Alerting

### Prometheus Metrics

```yaml
# Key metrics to monitor
- network_provider_requests_total           # Total requests
- network_provider_request_duration_seconds # Latency
- network_provider_resources_total          # Resource count
- network_provider_clusters_connected       # Cluster health
- network_provider_db_connections           # Database pool
```

### Alert Rules

```yaml
# prometheus-rules.yaml
groups:
  - name: network-provider
    rules:
      - alert: NetworkProviderDown
        expr: up{job="network-provider"} == 0
        for: 2m
        annotations:
          summary: "Network Provider is down"
          
      - alert: ClusterUnreachable
        expr: network_provider_clusters_connected < 3
        for: 5m
        annotations:
          summary: "One or more clusters unreachable"
          
      - alert: HighErrorRate
        expr: rate(network_provider_errors_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate (>5%)"
          
      - alert: DatabasePoolExhausted
        expr: network_provider_db_pool_used == network_provider_db_pool_size
        for: 1m
        annotations:
          summary: "Database connection pool exhausted"
          action: "Scale Database Pool or reduce connections"
```

### Dashboard Example (Grafana)

```
┌──────────────────────────────────────────────┐
│ Network Provider Status                      │
├──────────────────────────────────────────────┤
│ Status: ✅ Healthy                            │
│ Clusters: 3/3 connected                      │
│ Database: Connected (pool: 15/20)            │
├──────────────────────────────────────────────┤
│                                              │
│ Requests (last hour)                         │
│ ├─ Total: 12,345                             │
│ ├─ Success: 12,210 (99.1%)                   │
│ └─ Errors: 135 (1.1%)                        │
│                                              │
│ Resource Counts                              │
│ ├─ VNets: 234                                │
│ ├─ Subnets: 456                              │
│ ├─ NSGs: 189                                 │
│ └─ Load Balancers: 67                        │
│                                              │
│ IP Pool Utilization                          │
│ ├─ Storage: 125/128 (97.7%)  [!]             │
│ ├─ Data: 98/128 (76.6%)                      │
│ └─ Compute: 102/128 (79.7%)                  │
│                                              │
│ API Latency (p95)                            │
│ └─ 245ms                                     │
└──────────────────────────────────────────────┘
```

---

## Backup & Disaster Recovery

### Automated Backups

```bash
# Backup job (runs daily at 2 AM UTC)
kubectl create cronjob backup-database \
  --image=postgres:14 \
  --schedule="0 2 * * *" \
  -- sh -c 'pg_dump $DATABASE_URL | aws s3 cp - s3://backups/network-provider-$(date +%Y%m%d).sql'
```

### Restore Procedure

```bash
# 1. List available backups
aws s3 ls s3://backups/ | grep network-provider

# 2. Restore from backup
aws s3 cp s3://backups/network-provider-20260605.sql - | \
  psql network_provider

# 3. Verify restoration
psql network_provider -c "SELECT count(*) FROM resources;"

# 4. Restart Network Provider
kubectl rollout restart deployment/network-provider -n itl-network
```

### RTO/RPO Targets

```
RTO (Recovery Time Objective): 15 minutes
├─ Database restore: 5 minutes
├─ Network Provider restart: 2 minutes
└─ Cluster re-sync: 8 minutes

RPO (Recovery Point Objective): 1 hour
├─ Hourly backups
├─ Point-in-time recovery supported
└─ Transaction logs retained for 7 days
```

---

## Capacity Planning

### Growth Projections

```
Month 1: 50 subscriptions, 500 resources
Month 3: 150 subscriptions, 1,500 resources
Month 6: 400 subscriptions, 4,000 resources
Month 12: 1,000 subscriptions, 10,000 resources

Scaling needs:
├─ Database: Upgrade to 8-core, 32GB RAM at month 6
├─ Network Provider: Scale to 5 replicas at month 3
├─ IP Pools: Add new VLANs at month 6
└─ Cluster nodes: Add 50% capacity at month 3, 100% at month 6
```

### Proactive Upgrades

```bash
# Monitor usage trends
SELECT DATE(created_at) as date, COUNT(*) as resources_created
FROM resources
WHERE created_at > NOW() - INTERVAL '90 days'
GROUP BY DATE(created_at)
ORDER BY date;

# If trend shows 20% growth per month:
# → Schedule capacity increase 2 months ahead
# → Test scaling in staging
# → Coordinate with team for maintenance window
```

---

## Upgrades & Maintenance

### Blue-Green Deployment

```bash
# 1. Deploy new version to "green" environment
kubectl set image deployment/network-provider-green \
  network-provider=registry.local/itl/network-provider:0.2.0 \
  -n itl-network

# 2. Run smoke tests
./scripts/smoke-test.sh green

# 3. Switch traffic to green
kubectl patch service network-provider \
  -p '{"spec":{"selector":{"deployment":"green"}}}' \
  -n itl-network

# 4. Monitor for errors
watch 'curl http://localhost:8002/health | jq .'

# 5. If successful, delete old "blue" deployment
kubectl delete deployment network-provider-blue -n itl-network

# 6. If issues, rollback (switch back to blue)
kubectl patch service network-provider \
  -p '{"spec":{"selector":{"deployment":"blue"}}}' \
  -n itl-network
```

### Rolling Update (Alternative)

```bash
# Gradual update of replicas
kubectl set image deployment/network-provider \
  network-provider=registry.local/itl/network-provider:0.2.0 \
  -n itl-network

# Monitor rollout
kubectl rollout status deployment/network-provider -n itl-network -w
```

---

## On-Call Support

### Escalation Path

```
Level 1: Automated Monitoring & Alerts
├─ Healthy? → No action
└─ Unhealthy? → Page on-call engineer

Level 2: On-Call Engineer (1-hour response target)
├─ Check health dashboard
├─ Review logs
├─ Restart if needed
└─ If unresolved → Page engineering lead

Level 3: Engineering Lead (15-minute response target)
├─ Assess impact
├─ Decide on rollback vs. fix
├─ Engage development team
└─ If still critical → Page CTO
```

### Runbook Example

**Alert: High Error Rate**

```
1. Check health dashboard
   curl http://localhost:8002/health

2. Check recent changes
   git log --oneline -n 10 production

3. Review error logs
   kubectl logs deployment/network-provider -n itl-network --tail=100

4. Common causes:
   ├─ Database issue → Check connectivity
   ├─ Cluster unreachable → Test cluster connections
   ├─ Resource quota exceeded → Check database size
   └─ Code bug → Rollback to previous version

5. Recovery steps:
   ├─ Restart pods (if temporary glitch)
   ├─ Failover to backup cluster
   ├─ Rollback deployment
   └─ Engage engineering team
```

---

## Best Practices

### ✅ DO:

- ✅ Monitor health dashboard daily
- ✅ Schedule backups (hourly or more frequently)
- ✅ Test disaster recovery annually
- ✅ Plan capacity 2-3 months ahead
- ✅ Use GitOps for all deployments
- ✅ Document incident responses
- ✅ Share knowledge via runbooks

### ❌ DON'T:

- ❌ Make manual changes to production (always use Git)
- ❌ Skip monitoring or alerting
- ❌ Delete old backups (keep 1+ year)
- ❌ Deploy without testing in staging
- ❌ Ignore warning-level alerts
- ❌ Keep outdated documentation

---

## Next Steps

- **Security hardening?** → [Security & Best Practices](SECURITY.md)
- **Monitoring setup?** → [Monitoring Guide](../tasks/MONITORING.md)
- **Performance tuning?** → [Troubleshooting](../reference/TROUBLESHOOTING.md)

---

**Last Updated:** June 2026
