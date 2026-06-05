# Installation & Setup

Getting Network Provider up and running in your environment.

---

## Prerequisites

- **Kubernetes:** 3 clusters (Storage, Data, Compute) v1.28+
- **Cilium:** v1.15+ (with ClusterMesh enabled)
- **PostgreSQL:** 14+ (async connection support)
- **Docker Compose:** v2.20+ (for local development)
- **Python:** 3.12+ (for service)
- **itlc CLI:** Latest version (for management)

---

## Option 1: Local Development (Docker Compose)

### Quick Start (5 minutes)

```bash
# 1. Clone Network Provider
cd ~/projects
git clone https://github.com/ITlusions/ITL.ControlPlane.ResourceProvider.Network.git
cd ITL.ControlPlane.ResourceProvider.Network

# 2. Start services
docker compose up -d

# 3. Verify health
curl http://localhost:8002/health
# Output: {"status": "healthy", ...}

# 4. View logs
docker compose logs -f network-provider
```

### What Gets Started

```
Service             Port    Status
────────────────────────────────────
Network Provider    8002    Ready
PostgreSQL          5432    Ready
Redis Cache         6379    Ready
```

### First VNet (Test)

```bash
# 1. Get service token
TOKEN=$(curl -s http://localhost:8001/token -d '{"client_id":"admin"}' | jq -r '.access_token')

# 2. Create VNet
curl -X POST http://localhost:8002/subscriptions/sub-test/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/vnet-1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "properties": {
      "addressSpace": ["10.0.0.0/16"]
    }
  }'

# 3. Response
# HTTP 201 Created
# {
#   "id": "/subscriptions/sub-test/resourceGroups/rg-1/providers/Microsoft.Network/virtualNetworks/vnet-1",
#   "name": "vnet-1",
#   "type": "Microsoft.Network/virtualNetworks",
#   "properties": {
#     "addressSpace": ["10.0.0.0/16"],
#     "subnets": []
#   }
# }
```

---

## Option 2: Kubernetes Deployment (Production)

### Architecture

```
┌─────────────────────────────────────────────┐
│ Kubernetes Cluster (Compute)                │
│                                             │
│  ┌────────────────────────────────────┐    │
│  │ ITL Namespace                      │    │
│  │                                    │    │
│  │ ┌──────────────────────────────┐  │    │
│  │ │ Network Provider Pod         │  │    │
│  │ │ (Deployment: 3 replicas)     │  │    │
│  │ │ Port: 8002                   │  │    │
│  │ └──────────────────────────────┘  │    │
│  │                                    │    │
│  │ ┌──────────────────────────────┐  │    │
│  │ │ Redis Cache (StatefulSet)    │  │    │
│  │ │ Port: 6379                   │  │    │
│  │ └──────────────────────────────┘  │    │
│  └────────────────────────────────────┘    │
│                                             │
│  ┌────────────────────────────────────┐    │
│  │ PostgreSQL (External or In-Cluster)    │
│  │ Port: 5432                         │    │
│  │ (Recommendation: use RDS or managed) │  │
│  └────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

### Prerequisites

1. **PostgreSQL Database**
   ```bash
   # Create database and user
   psql -c "CREATE DATABASE network_provider;"
   psql -c "CREATE USER np_user WITH PASSWORD 'secure_password';"
   psql -c "GRANT ALL ON network_provider TO np_user;"
   ```

2. **Kubernetes Namespace**
   ```bash
   kubectl create namespace itl-network
   kubectl label namespace itl-network tenant=shared
   ```

3. **Secrets**
   ```bash
   # Database connection
   kubectl create secret generic db-credentials \
     --from-literal=url=postgresql://np_user:secure_password@postgres.default:5432/network_provider \
     -n itl-network

   # Keycloak OIDC
   kubectl create secret generic oidc-credentials \
     --from-literal=client-id=network-provider \
     --from-literal=client-secret=your-secret-here \
     -n itl-network

   # Service account tokens (for cluster communication)
   kubectl create secret generic cluster-credentials \
     --from-literal=storage-token=$(cat ~/.kube/storage-token) \
     --from-literal=data-token=$(cat ~/.kube/data-token) \
     --from-literal=compute-token=$(cat ~/.kube/compute-token) \
     -n itl-network
   ```

### Deployment Steps

1. **Build Docker Image**
   ```bash
   docker build -t itl/network-provider:0.1.0 .
   docker tag itl/network-provider:0.1.0 registry.local/itl/network-provider:latest
   docker push registry.local/itl/network-provider:latest
   ```

2. **Deploy Using Helm**
   ```bash
   helm repo add itl https://helm.itlusions.com
   helm install network-provider itl/network-provider \
     --namespace itl-network \
     --values values.prod.yaml
   ```

   Or using Kustomize:
   ```bash
   kubectl apply -k deployment/kustomize/overlays/production -n itl-network
   ```

3. **Verify Deployment**
   ```bash
   kubectl rollout status deployment/network-provider -n itl-network
   kubectl get pods -n itl-network
   # Should show 3 network-provider pods in Running state
   ```

4. **Test Health**
   ```bash
   kubectl port-forward svc/network-provider 8002:8002 -n itl-network
   curl http://localhost:8002/health
   ```

### Helm Values (Example)

```yaml
# values.prod.yaml
replicaCount: 3

image:
  repository: registry.local/itl/network-provider
  tag: 0.1.0
  pullPolicy: IfNotPresent

resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 2
    memory: 2Gi

database:
  existingSecret: db-credentials
  secretKey: url

oidc:
  issuer: https://keycloak.itlusions.com/auth/realms/itlusions
  clientId: network-provider
  existingSecret: oidc-credentials

clusters:
  - name: storage
    kubeconfig: /var/run/secrets/storage/kubeconfig
    bgp:
      as: 65000
      vlan: 100
  - name: data
    kubeconfig: /var/run/secrets/data/kubeconfig
    bgp:
      as: 65001
      vlan: 200
  - name: compute
    kubeconfig: /var/run/secrets/compute/kubeconfig
    bgp:
      as: 65002
      vlan: 300

service:
  type: ClusterIP
  port: 8002
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8002"
    prometheus.io/path: "/metrics"
```

---

## Environment Configuration

### Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://np_user:password@postgres:5432/network_provider
DATABASE_POOL_SIZE=20
DATABASE_ECHO=false

# Keycloak OIDC
KEYCLOAK_URL=https://keycloak.itlusions.com
KEYCLOAK_REALM=itlusions
OIDC_CLIENT_ID=network-provider
OIDC_CLIENT_SECRET=secret-here

# Cluster Configuration
CLUSTER_CONFIG_PATH=/etc/network-provider/clusters.json
# Contents: [{name: "storage", kubeconfig_path: "/etc/kube/storage.conf", ...}]

# API
API_PORT=8002
API_LOG_LEVEL=INFO
```

### Optional Configuration

```bash
# Redis caching
REDIS_URL=redis://redis:6379
REDIS_CACHE_TTL=300

# Observability
PROMETHEUS_ENABLED=true
JAEGER_ENABLED=true
JAEGER_ENDPOINT=http://jaeger:6831

# Security
ENABLE_MTLS=false
CERT_PATH=/etc/tls/certs
KEY_PATH=/etc/tls/private

# Feature flags
ENABLE_PRIVATE_LINK=true
ENABLE_BGP_PEERING=true
```

---

## Database Migration

### Initialize Database

```bash
# Run Alembic migrations
alembic upgrade head

# Verify tables created
psql -c "\dt" network_provider
# Output: audit_logs, resources, subscriptions, ...
```

### Backup & Restore

```bash
# Backup
pg_dump network_provider | gzip > backup-$(date +%Y%m%d).sql.gz

# Restore
gunzip backup-20260605.sql.gz
psql network_provider < backup-20260605.sql
```

---

## Multi-Cluster Setup

### Step 1: Gather Cluster Information

```bash
# For each cluster (storage, data, compute):
CLUSTER_NAME=storage
KUBECONFIG=~/.kube/${CLUSTER_NAME}

# Get cluster endpoint
kubectl cluster-info --kubeconfig=$KUBECONFIG | grep 'Kubernetes master'
# Output: Kubernetes master is running at https://api.storage.cluster:6443

# Get service account token
kubectl get secret -n default $(kubectl get secret -n default -o name | head -1) \
  -o jsonpath='{.data.token}' | base64 -d > /tmp/${CLUSTER_NAME}-token

# Create ClusterRole (if not exists)
kubectl create clusterrole network-provider-admin \
  --verb=get,list,watch,create,update,patch,delete \
  --resource=ciliumloadbalancerippools,ciliumnetworkpolicies,ciliumpeerings \
  --kubeconfig=$KUBECONFIG

# Create ClusterRoleBinding
kubectl create clusterrolebinding network-provider-admin \
  --clusterrole=network-provider-admin \
  --serviceaccount=default:network-provider \
  --kubeconfig=$KUBECONFIG
```

### Step 2: Configure ClusterMesh

```bash
# Enable ClusterMesh on each cluster
for CLUSTER in storage data compute; do
  kubectl --kubeconfig=~/.kube/$CLUSTER \
    exec -it -n kube-system ds/cilium \
    -- cilium clustermesh enable

  # Wait for mesh to be ready
  kubectl --kubeconfig=~/.kube/$CLUSTER \
    wait --for=condition=ready pod -l k8s-app=cilium -n kube-system --timeout=300s
done
```

### Step 3: Configure BGP Peering

```bash
# For each cluster, configure BGP
kubectl apply -f - <<EOF
apiVersion: cilium.io/v2alpha1
kind: CiliumBGPPeeringPolicy
metadata:
  name: bgp-peering
spec:
  nodeSelectors:
    - matchExpressions:
        - key: bgp-node
          operator: In
          values:
            - "true"
  virtualRouters:
    - localASN: 65000  # different for each cluster
      exportPodCIDR: true
      neighbors:
        - peerAddress: 10.1.1.254  # Your router IP
          peerASN: 64512            # Your network AS
          families:
            - afi: ipv4
              safi: unicast
EOF
```

---

## Verification Checklist

```bash
# 1. Service is running
curl http://localhost:8002/health

# 2. Database connected
curl http://localhost:8002/health | jq '.database'
# Output: "connected"

# 3. All clusters connected
curl http://localhost:8002/health | jq '.clusters'
# Output: {"storage": "connected", "data": "connected", "compute": "connected"}

# 4. Can create resources
curl -X POST http://localhost:8002/subscriptions/test/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/test-vnet \
  -H "Authorization: Bearer $TOKEN" \
  -d '...'
# Should return 201 Created

# 5. Resource deployed to all clusters
for CLUSTER in storage data compute; do
  kubectl --kubeconfig=~/.kube/$CLUSTER get ciliumloadbalancerippools -n test
  # Should show the created resource
done
```

---

## Troubleshooting Installation

### Service won't start

```bash
# Check logs
docker compose logs network-provider
# or
kubectl logs deployment/network-provider -n itl-network

# Common issues:
# - Database connection error → Check DATABASE_URL
# - Missing Keycloak → Check KEYCLOAK_URL
# - Port already in use → Change API_PORT
```

### Clusters not connecting

```bash
# Check cluster kubeconfig files
ls -la /etc/network-provider/kubeconfig/

# Test cluster connectivity
kubectl --kubeconfig=/etc/network-provider/kubeconfig/storage cluster-info

# Verify service account permissions
kubectl auth can-i get ciliumloadbalancerippools --as=system:serviceaccount:default:network-provider \
  --kubeconfig=/etc/network-provider/kubeconfig/storage
```

### Database migration fails

```bash
# Check current revision
alembic current

# Rollback to previous
alembic downgrade -1

# Re-apply migration
alembic upgrade head

# View migration history
alembic history
```

---

## Upgrade Path

### From 0.0.x to 0.1.0

```bash
# 1. Backup database
pg_dump network_provider > backup-pre-upgrade.sql

# 2. Pull new version
docker pull registry.local/itl/network-provider:0.1.0

# 3. Run migrations
docker run --rm -e DATABASE_URL=... \
  registry.local/itl/network-provider:0.1.0 \
  alembic upgrade head

# 4. Restart service
docker compose up -d --force-recreate network-provider
# or
kubectl rollout restart deployment/network-provider -n itl-network

# 5. Verify
curl http://localhost:8002/health
```

---

## Next Steps

- **Configure security?** → [Security Setup](SECURITY.md)
- **Setup for production?** → [Production Deployment](PRODUCTION_DEPLOYMENT.md)
- **Ready to use?** → [Getting Started](../guides/GETTING_STARTED.md)

---

**Last Updated:** June 2026
