# Configuration Guide

## Environment Variables

### Service Configuration

| Variable | Default | Description |
|---|---|---|
| `NETWORK_PROVIDER_PORT` | `8002` | Port for FastAPI server |
| `NETWORK_PROVIDER_HOST` | `0.0.0.0` | Host to bind to |
| `LOG_LEVEL` | `info` | Logging level (debug, info, warning, error) |

### Kubernetes Cluster Endpoints

The provider connects to **three Kubernetes clusters** simultaneously: storage, data, and compute.

| Variable | Default | Description |
|---|---|---|
| `STORAGE_CLUSTER_ENDPOINT` | `http://localhost:8001` | Storage cluster API endpoint |
| `DATA_CLUSTER_ENDPOINT` | `http://localhost:8001` | Data cluster API endpoint |
| `COMPUTE_CLUSTER_ENDPOINT` | `http://localhost:8001` | Compute cluster API endpoint |

**Example** (docker-compose):
```yaml
environment:
  STORAGE_CLUSTER_ENDPOINT: http://storage-cluster:6443
  DATA_CLUSTER_ENDPOINT: http://data-cluster:6443
  COMPUTE_CLUSTER_ENDPOINT: http://compute-cluster:6443
```

### Cilium Configuration

| Variable | Default | Description |
|---|---|---|
| `CILIUM_NAMESPACE` | `kube-system` | Namespace where Cilium is deployed |
| `CILIUM_VERSION` | `1.14.0` | Expected Cilium version (for compatibility) |

### Database Configuration

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:pass@localhost:5432/network_provider` | PostgreSQL connection string |
| `DATABASE_POOL_SIZE` | `20` | SQLAlchemy connection pool size |
| `DATABASE_ECHO` | `false` | Log SQL statements (debug only) |

**Example**:
```bash
export DATABASE_URL="postgresql://provider:password@postgres:5432/itl_network"
```

### Authentication & Authorization

| Variable | Default | Description |
|---|---|---|
| `KEYCLOAK_URL` | `https://sts.itlusions.com` | Keycloak server URL |
| `KEYCLOAK_REALM` | `itlusions` | Keycloak realm |
| `TOKEN_VALIDATION_ENABLED` | `true` | Enable JWT token validation |

### Resource Naming

| Variable | Default | Description |
|---|---|---|
| `RESOURCE_PREFIX` | `itl` | Prefix for generated K8s names |
| `ENABLE_DETERMINISTIC_NAMING` | `true` | Use MD5-based deterministic naming |

## Multi-Cluster Deployment

The provider deploys resources to **all three clusters simultaneously**:

1. **Storage Cluster**: Persistent data resources
2. **Data Cluster**: Data processing resources
3. **Compute Cluster**: Stateless compute resources

This multi-cluster deployment ensures:
- [x] High availability across availability zones
- [x] Automatic failover if one cluster is down
- [x] Distributed load across clusters

### Cluster Configuration Example

```bash
# Set cluster endpoints (usually configured via Kubernetes secret)
export STORAGE_CLUSTER_ENDPOINT=https://storage-cluster.example.com:6443
export DATA_CLUSTER_ENDPOINT=https://data-cluster.example.com:6443
export COMPUTE_CLUSTER_ENDPOINT=https://compute-cluster.example.com:6443

# Kubernetes auth token (optional, can use in-cluster auth)
export KUBECONFIG=/etc/kubernetes/config
```

### Docker Compose with Multi-Cluster

```yaml
version: '3.9'

services:
  network-provider:
    image: itl-network-provider:latest
    ports:
      - "8002:8002"
    environment:
      STORAGE_CLUSTER_ENDPOINT: http://storage-cluster:6443
      DATA_CLUSTER_ENDPOINT: http://data-cluster:6443
      COMPUTE_CLUSTER_ENDPOINT: http://compute-cluster:6443
      DATABASE_URL: postgresql://provider:password@postgres:5432/network_db
      CILIUM_NAMESPACE: kube-system
    depends_on:
      - postgres
      - storage-cluster
      - data-cluster
      - compute-cluster

  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: provider
      POSTGRES_PASSWORD: password
      POSTGRES_DB: network_db
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

## Multi-Subscription Isolation

### Namespace Mapping

Each subscription gets its own Kubernetes namespace for isolation:

```
Subscription ID          K8s Namespace       CIDR Space
sub-00000001            sub-00000001        10.0.0.0/16 (overlapping allowed)
sub-00000002            sub-00000002        10.0.0.0/16 (same as sub-1, isolated)
sub-00000003            sub-00000003        10.0.0.0/16 (same CIDR, all isolated)
```

This allows **different subscriptions to use overlapping IP ranges** without conflicts due to Kubernetes namespace isolation.

### Cilium Policies for Isolation

Network policies are created in **both** the source and destination namespaces:

```yaml
# In producer namespace (sub-00000001)
CiliumNetworkPolicy:
  - name: allow-private-link-out
    fromEndpoints:
      - matchLabels:
          app: producer-service

# In consumer namespace (sub-00000002)
CiliumNetworkPolicy:
  - name: allow-private-link-in
    toEndpoints:
      - matchLabels:
          app: consumer-endpoint
```

## Troubleshooting Configuration

### Debug Logging

Enable debug logging for detailed request/response logs:

```bash
export LOG_LEVEL=debug
```

### SQL Statement Logging

Log all SQL queries (careful in production):

```bash
export DATABASE_ECHO=true
```

### Kubernetes API Debugging

Enable verbose logging for K8s API calls:

```bash
export KUBERNETES_LOGLEVEL=debug
```

## Security Best Practices

1. **Never commit secrets to git**:
   - Store in `.env` file (git-ignored)
   - Use Kubernetes Secrets for deployed services
   - Use Keycloak for token management

2. **Token validation**:
   - Set `TOKEN_VALIDATION_ENABLED=true` (default)
   - Keycloak validates all API requests

3. **Database passwords**:
   - Use strong passwords (min 32 chars)
   - Rotate regularly
   - Don't log the full connection string

4. **Cluster endpoints**:
   - Use HTTPS with valid certificates
   - Use service accounts instead of passwords
   - Implement network policies to restrict access

## Production Checklist

- [ ] All cluster endpoints configured and reachable
- [ ] Database with backups enabled
- [ ] Keycloak realm configured for token validation
- [ ] Log level set to `info` (not `debug`)
- [ ] Database pool size tuned to workload
- [ ] Monitoring and alerts configured
- [ ] Secrets stored in external vault (not env vars)
- [ ] Multi-cluster deployment tested
