# Production Deployment

Deploying Network Provider to production with high availability, monitoring, and operational excellence.

---

## Pre-Deployment Checklist

### Infrastructure Prerequisites

```
Kubernetes:
   3 Kubernetes clusters (Storage, Data, Compute) v1.28+
   Cilium v1.15+ with ClusterMesh enabled
   BGP enabled on clusters for external IP advertisement
   All nodes labeled (bgp-node=true)
   All nodes have sufficient resources (4 CPU, 8GB RAM minimum)

Storage:
   PostgreSQL 14+ with replication enabled
   Backups configured (daily automated)
   Connection pooling (pgBouncer) on database
   Read replicas for scaling queries

Networking:
   VLAN(s) provisioned for external IPs
   BGP peering configured with network devices
   Firewall rules allow pod egress
   Load balancers support BGP route announcement

Security:
   Keycloak/OIDC server configured
   TLS certificates (let's Encrypt or CA)
   Secret management (Vault/sealed-secrets)
   Network policies templates ready

Monitoring:
   Prometheus installed in all clusters
   Grafana for visualization
   Alertmanager configured
   Log aggregation (Loki/ELK)
```

---

## Deployment Strategy

### Phase 1: Staging Environment (Week 1)

```bash
# 1. Deploy to staging clusters with test data
docker build -t registry.local/itl/network-provider:0.1.0 .
docker push registry.local/itl/network-provider:0.1.0

# 2. Deploy via Helm (staging values)
helm install network-provider ./helm \
  --namespace itl-network \
  --values values.staging.yaml \
  --wait

# 3. Run acceptance tests
./scripts/run-acceptance-tests.sh staging

# 4. Load test
./scripts/load-test.sh --target staging --duration 1h --rps 1000

# 5. Chaos engineering (kill random pods, clusters)
./scripts/chaos-test.sh staging
```

### Phase 2: Canary Deployment (Day 1)

```bash
# 1. Deploy to 10% of traffic (1 replica out of 10)
kubectl set image deployment/network-provider \
  network-provider=registry.local/itl/network-provider:0.1.0 \
  -n itl-network

# 2. Monitor metrics closely
watch 'kubectl top pod -n itl-network'
prometheus_query 'rate(network_provider_errors_total[5m])'

# 3. If error rate < 0.1%, proceed to full rollout
```

### Phase 3: Full Production Rollout (Day 2-3)

```bash
# 1. Scale to 3 replicas
kubectl scale deployment/network-provider --replicas=3 -n itl-network

# 2. Verify all replicas healthy
kubectl get pods -n itl-network -w

# 3. Enable autoscaling
kubectl autoscale deployment network-provider \
  --min=3 --max=10 \
  --cpu-percent=70 \
  -n itl-network

# 4. Monitor production for 24 hours
watch 'curl http://localhost:8002/health'
```

---

## High Availability Configuration

### Multi-Replica Setup

```yaml
# Kubernetes Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: network-provider
  namespace: itl-network
spec:
  replicas: 3  # HA minimum
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1       # 1 new pod during update
      maxUnavailable: 0 # Never drop all replicas
  selector:
    matchLabels:
      app: network-provider
  template:
    metadata:
      labels:
        app: network-provider
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchExpressions:
                  - key: app
                    operator: In
                    values:
                      - network-provider
              topologyKey: kubernetes.io/hostname
      containers:
        - name: network-provider
          image: registry.local/itl/network-provider:0.1.0
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: 2
              memory: 2Gi
          livenessProbe:
            httpGet:
              path: /health
              port: 8002
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /ready
              port: 8002
            initialDelaySeconds: 10
            periodSeconds: 5
            timeoutSeconds: 5
            failureThreshold: 1
          env:
            - name: DATABASE_POOL_SIZE
              value: "20"
            - name: API_LOG_LEVEL
              value: "INFO"
            # ... other env vars from secrets
```

### Database High Availability

```
Primary (Active)
     Replication stream
Standby 1 (Hot standby)
     Replication stream
Standby 2 (Hot standby)

Automatic failover:
  Primary goes down  Standby 1 promoted  Standby 2 connects to new primary
```

**Configuration:**
```bash
# PostgreSQL replication settings
max_wal_senders = 3
wal_level = replica
hot_standby = on

# Create replication slots
CREATE_REPLICATION_SLOT primary_slot PHYSICAL

# Check replication status
SELECT * FROM pg_stat_replication;
```

### Service High Availability

```yaml
apiVersion: v1
kind: Service
metadata:
  name: network-provider
  namespace: itl-network
spec:
  type: ClusterIP
  clusterIP: 10.0.0.50    # Fixed IP for internal access
  sessionAffinity: ClientIP # Session stickiness (optional)
  selector:
    app: network-provider
  ports:
    - port: 8002
      targetPort: 8002
      protocol: TCP
---
# Optional: LoadBalancer for external access
apiVersion: v1
kind: Service
metadata:
  name: network-provider-lb
  namespace: itl-network
spec:
  type: LoadBalancer
  selector:
    app: network-provider
  ports:
    - port: 443
      targetPort: 8002
      protocol: TCP
  loadBalancerIP: 10.200.0.100  # VLAN IP
```

---

## Monitoring & Observability

### Prometheus Setup

```yaml
# Scrape config for Network Provider
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'network-provider'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - itl-network
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: network-provider
      - source_labels: [__meta_kubernetes_pod_port_name]
        action: keep
        regex: metrics
```

### Key Alerts

```yaml
groups:
  - name: network-provider
    interval: 30s
    rules:
      # Availability
      - alert: NetworkProviderDown
        expr: up{job="network-provider"} == 0
        for: 2m
        annotations:
          severity: critical
          summary: Network Provider is down

      # Cluster connectivity
      - alert: ClusterUnreachable
        expr: network_provider_clusters_connected < 3
        for: 5m
        annotations:
          severity: critical
          
      # Error rate
      - alert: HighErrorRate
        expr: rate(network_provider_errors_total[5m]) > 0.01
        for: 5m
        annotations:
          severity: warning
          
      # Database
      - alert: DatabaseConnectionPoolExhausted
        expr: network_provider_db_pool_used == network_provider_db_pool_size
        for: 1m
        annotations:
          severity: critical
          action: "Increase pool size or reduce connections"
          
      # API latency
      - alert: HighAPILatency
        expr: histogram_quantile(0.95, network_provider_request_duration_seconds) > 1
        for: 5m
        annotations:
          severity: warning
```

### Logging

```bash
# Structured logging configuration
LOG_FORMAT=json
LOG_LEVEL=INFO
LOG_OUTPUT=stdout

# Example log entry
{
  "timestamp": "2026-06-05T12:34:56.789Z",
  "level": "INFO",
  "logger": "network_provider.api",
  "message": "Resource created",
  "event_id": "evt-12345",
  "user_id": "user-abc",
  "subscription_id": "sub-001",
  "resource_type": "virtualNetworks",
  "resource_name": "prod-vnet",
  "duration_ms": 245
}
```

---

## Backup & Recovery

### Automated Backups

```yaml
# Kubernetes CronJob for daily backups
apiVersion: batch/v1
kind: CronJob
metadata:
  name: backup-network-provider-db
  namespace: itl-network
spec:
  schedule: "2 * * * *"  # Every hour at :02
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: postgres:14
              env:
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: db-credentials
                      key: password
              command:
                - /bin/sh
                - -c
                - |
                  pg_dump -h $DB_HOST -U $DB_USER $DB_NAME | \
                  gzip > /backup/network-provider-$(date +%Y%m%d-%H%M%S).sql.gz
                  aws s3 cp /backup/*.sql.gz s3://backups/network-provider/
              volumeMounts:
                - name: backup-storage
                  mountPath: /backup
          volumes:
            - name: backup-storage
              emptyDir: {}
          restartPolicy: OnFailure
```

### Point-in-Time Recovery

```bash
# 1. List available backups
aws s3 ls s3://backups/network-provider/

# 2. Restore to point-in-time
BACKUP_TIME="2026-06-05T12:00:00Z"

# Restore backup
aws s3 cp s3://backups/network-provider/network-provider-20260605-120000.sql.gz - | \
  gunzip | psql -h $DB_HOST -U $DB_USER network_provider

# Apply WAL logs up to point-in-time (if needed)
# restore_command = 'aws s3 cp s3://backups/wal/%f %p'
```

---

## Performance Tuning

### Database Optimization

```sql
-- Connection pooling (pgBouncer)
-- clients = 1000
-- default_pool_size = 25
-- max_db_connections = 100

-- Key indexes
CREATE INDEX CONCURRENTLY idx_resources_subscription ON resources(subscription_id);
CREATE INDEX CONCURRENTLY idx_resources_type ON resources(resource_type);
CREATE INDEX CONCURRENTLY idx_audit_logs_timestamp ON audit_logs(created_at);

-- Table partitioning (for audit logs growth)
CREATE TABLE audit_logs (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMP,
  ...
) PARTITION BY RANGE (created_at) (
  PARTITION logs_2026_q1 VALUES FROM ('2026-01-01') TO ('2026-04-01'),
  PARTITION logs_2026_q2 VALUES FROM ('2026-04-01') TO ('2026-07-01'),
  ...
);

-- Vacuum settings
VACUUM_COST_DELAY = 50ms
VACUUM_COST_LIMIT = 10000
```

### API Performance

```python
# Connection pooling
DATABASE_POOL_SIZE = 20           # Connections per replica
DATABASE_MAX_OVERFLOW = 10        # Additional connections if pool exhausted
DATABASE_POOL_TIMEOUT = 30        # Wait 30s for connection

# Caching
REDIS_CACHE_TTL = 300             # 5 minutes
CACHE_KEY = f"resource:{resource_id}"

# Request batching
MAX_BATCH_SIZE = 100              # Max items per request
```

### Cluster Resource Allocation

```yaml
# Node requirements
apiVersion: v1
kind: Node
metadata:
  labels:
    workload-type: network-provider
spec:
  capacity:
    cpu: 16
    memory: 64Gi
  allocatable:
    cpu: 15500m           # Reserve 500m for system
    memory: 61Gi

# Pod resource limits
Network Provider pod:
  requests: 500m CPU, 512Mi memory
  limits: 2 CPU, 2Gi memory
  
Redis cache pod:
  requests: 100m CPU, 256Mi memory
  limits: 500m CPU, 1Gi memory
```

---

## GitOps Deployment

### Flux CD Setup

```yaml
# Install Flux
flux bootstrap github \
  --owner=ITlusions \
  --repo=infrastructure \
  --path=clusters/prod \
  --personal

# Create source for Network Provider Helm chart
apiVersion: source.toolkit.fluxcd.io/v1beta1
kind: HelmRepository
metadata:
  name: network-provider
  namespace: flux-system
spec:
  interval: 1h
  url: https://helm.itlusions.com
---
# Create HelmRelease to deploy
apiVersion: helm.toolkit.fluxcd.io/v2beta1
kind: HelmRelease
metadata:
  name: network-provider
  namespace: itl-network
spec:
  interval: 1h
  chart:
    spec:
      chart: network-provider
      sourceRef:
        kind: HelmRepository
        name: network-provider
      version: 0.1.x
  values:
    replicaCount: 3
    image:
      repository: registry.local/itl/network-provider
      tag: 0.1.0
  postRenderers:
    - kustomize:
        patchesStrategicMerge:
          - kind: Deployment
            apiVersion: apps/v1
            metadata:
              name: network-provider
            spec:
              replicas: 3  # Override for prod
```

---

## Rollback Procedure

### Emergency Rollback

```bash
# 1. Detect issue (high error rate, pod crashes, etc.)
kubectl get pods -n itl-network
# OUTPUT: 2 running, 1 CrashLoopBackOff

# 2. Immediate rollback
kubectl rollout undo deployment/network-provider -n itl-network

# 3. Verify recovery
kubectl get pods -n itl-network
kubectl logs deployment/network-provider -n itl-network --tail=20

# 4. Check if issue resolved
curl http://localhost:8002/health

# 5. Post-incident review
# - Why was it deployed with the issue?
# - How to detect in testing?
# - How to prevent recurrence?
```

### Database Rollback

```bash
# 1. Identify corrupted state
SELECT * FROM resources WHERE id = 'bad-resource';

# 2. Restore from backup
./restore-database.sh --from-time 2026-06-05T10:00:00Z

# 3. Verify data integrity
./verify-database-integrity.sh

# 4. Notify affected customers (if any data loss)
```

---

## Cost Optimization

### Resource Efficiency

```
Current Setup:
 Network Provider: 3 replicas  500m CPU = 1.5 CPU requested
 Database: 4 cores, 32GB RAM
 Total: ~6 CPU, 40GB RAM

Optimizations:
 Use spot instances for non-critical components (20% savings)
 CPU request: 300m  250m (use actual average + 20% buffer)
 Memory: 512Mi  256Mi (profiles show peak is 150Mi)
 Estimated savings: 30% = $X,000/month
```

### Scaling by Load

```
Low traffic (night):
 Network Provider: 1 replica
 Database: Single instance
 Cost: Minimum

High traffic (day):
 Network Provider: 5 replicas
 Database: Read replicas active
 Cost: Peak
```

---

## Success Criteria (Go/No-Go)

### Pre-Production Sign-Off

```
Performance:
   API latency p95 < 200ms
   Throughput > 1,000 req/s
   Error rate < 0.1%
   Zero data loss in 7-day test

Reliability:
   All clusters connected (3/3)
   No pod crashes in 7 days
   Database replication verified
   Backup/restore tested

Security:
   All traffic encrypted (TLS)
   OIDC authentication working
   RBAC policies enforced
   Audit logs recording all changes

Operations:
   Monitoring alerts functional
   On-call runbooks written
   Team trained on procedures
   Rollback procedure tested

Compliance:
   Security audit completed
   Penetration test passed
   Data residency verified
   Compliance certifications met
```

---

## Next Steps

- **Operations guide?**  [For Operators](../guides/FOR_OPERATORS)
- **Security setup?**  [Security & Best Practices](SECURITY)
- **Architecture details?**  [Architecture](../concepts/ARCHITECTURE)

---

**Last Updated:** June 2026
