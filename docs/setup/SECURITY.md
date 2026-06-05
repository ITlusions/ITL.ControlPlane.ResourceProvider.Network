# Security & Best Practices

Security hardening and operational best practices for Network Provider.

---

## Authentication & Authorization

### OIDC Setup (Keycloak)

```yaml
# 1. Register client in Keycloak
Realm: itlusions
Client ID: network-provider
Client Secret: [auto-generated]
Access Type: confidential
Standard Flow Enabled: true
Valid Redirect URIs:
  - http://localhost:8002/oauth/callback
  - https://network-api.itlusions.com/oauth/callback
```

### Token Scopes

```bash
# Request specific scopes
TOKEN=$(curl -s https://keycloak.itlusions.com/auth/realms/itlusions/protocol/openid-connect/token \
  -d client_id=network-provider \
  -d client_secret=secret \
  -d scope="openid profile email" \
  -d grant_type=client_credentials)
```

### Service-to-Service Authentication

```bash
# Network Provider  Kubernetes API
# Use service account tokens (in kubeconfig)

# Network Provider  PostgreSQL
# Use connection string with credentials
DATABASE_URL=postgresql://np_user:password@postgres:5432/network_provider
# Never commit passwords to Git!

# Use environment variables or secrets management:
DATABASE_URL=$(aws secretsmanager get-secret-value --secret-id db-credentials | jq -r .SecretString)
```

---

## Network Security

### Ingress Controller

```yaml
# Kubernetes Ingress (TLS termination)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: network-provider-ingress
  namespace: itl-network
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - network-api.itlusions.com
      secretName: network-provider-tls
  rules:
    - host: network-api.itlusions.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: network-provider
                port:
                  number: 8002
```

### Rate Limiting

```yaml
# CloudFlare rate limiting (or nginx)
actions:
  - type: block
    evaluation: "num_requests >= 1000"
    period: 60  # seconds
    description: "Block after 1000 requests per minute"
```

### Network Policies (Kubernetes)

```yaml
# Restrict traffic to Network Provider pods
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: network-provider-access
  namespace: itl-network
spec:
  podSelector:
    matchLabels:
      app: network-provider
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8002
  egress:
    # Allow DNS
    - to:
        - namespaceSelector:
            matchLabels:
              name: kube-system
      ports:
        - protocol: UDP
          port: 53
    # Allow PostgreSQL
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - protocol: TCP
          port: 5432
    # Allow Kubernetes API
    - to:
        - namespaceSelector: {}
      ports:
        - protocol: TCP
          port: 6443
```

---

## Data Protection

### Database Encryption

```bash
# Enable PostgreSQL SSL
# In postgresql.conf:
ssl = on
ssl_cert_file = '/etc/ssl/certs/server.crt'
ssl_key_file = '/etc/ssl/private/server.key'

# Connection string with SSL
DATABASE_URL=postgresql://np_user:password@postgres:5432/network_provider?sslmode=require
```

### Secrets Management

```bash
# Use HashiCorp Vault (or similar)
VAULT_ADDR=https://vault.itlusions.com
VAULT_TOKEN=$(cat /var/run/secrets/vault/token)

# Retrieve secrets
curl -H "X-Vault-Token: $VAULT_TOKEN" \
  $VAULT_ADDR/v1/secret/data/network-provider/database | jq '.data.data.url'
```

### Backup Encryption

```bash
# Backup with encryption
pg_dump network_provider | \
  openssl enc -aes-256-cbc -pass pass:backup-key | \
  gzip > backup-encrypted.sql.gz

# Restore
gunzip backup-encrypted.sql.gz | \
  openssl enc -d -aes-256-cbc -pass pass:backup-key | \
  psql network_provider
```

---

## Input Validation

### Request Validation

All incoming requests are validated:

```python
# Example: VNet creation
class CreateVNetRequest(BaseModel):
    properties: VNetProperties
    
    class Config:
        # Pydantic validation
        json_schema_extra = {
            "example": {
                "properties": {
                    "addressSpace": ["10.0.0.0/16"]
                }
            }
        }

class VNetProperties(BaseModel):
    addressSpace: List[str]
    
    @validator('addressSpace')
    def validate_cidr(cls, v):
        for cidr in v:
            # Validate CIDR format
            ipaddress.ip_network(cidr)
        return v
```

### SQL Injection Prevention

```python
#  SAFE: Using parameterized queries
result = await db.execute(
    "SELECT * FROM resources WHERE id = :id AND subscription_id = :sub",
    {"id": resource_id, "sub": subscription_id}
)

#  UNSAFE: String concatenation
result = await db.execute(
    f"SELECT * FROM resources WHERE id = '{resource_id}'"
)
```

---

## Audit & Logging

### Audit Log Configuration

```python
# All state-changing operations logged
@app.post("/subscriptions/{sub}/...")
async def create_resource(
    sub: str,
    request: CreateResourceRequest,
    user: User = Depends(get_current_user)
):
    # Create resource...
    
    # Log audit event
    await audit_log.record(
        action="Create",
        resource_type=request.type,
        resource_id=resource.id,
        user_id=user.id,
        changes={"created": resource.dict()},
        timestamp=datetime.utcnow(),
        status="Success"
    )
```

### Log Retention

```bash
# Keep audit logs for 7 years (compliance)
# PostgreSQL table partitioning by month
CREATE TABLE audit_logs_2026_06 PARTITION OF audit_logs
  FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

# Automated cleanup
DELETE FROM audit_logs WHERE created_at < NOW() - INTERVAL '7 years';
```

### Sensitive Data Masking

```python
# Never log passwords, tokens, etc.
def mask_sensitive_fields(data: dict) -> dict:
    sensitive_keys = ['password', 'secret', 'token', 'api_key']
    for key in data:
        if any(s in key.lower() for s in sensitive_keys):
            data[key] = '***REDACTED***'
    return data

# Usage
logger.info(f"Request: {mask_sensitive_fields(request.dict())}")
```

---

## Compliance & Regulations

### GDPR Compliance

- [x] User data only stored if necessary
- [x] Data deletion on request (right to be forgotten)
- [x] Audit logs track who accessed what
- [x] Data minimization (don't store unnecessary fields)

```python
@app.delete("/subscriptions/{sub}/user-data")
async def delete_user_data(sub: str, user: User):
    # Find all resources owned by user
    resources = await db.execute(
        "SELECT * FROM resources WHERE owner_id = :user_id",
        {"user_id": user.id}
    )
    
    # Delete each resource
    for resource in resources:
        await db.execute(
            "DELETE FROM resources WHERE id = :id",
            {"id": resource.id}
        )
    
    # Log deletion
    await audit_log.record(
        action="Delete",
        resource_type="user_data",
        reason="GDPR right to be forgotten"
    )
```

### SOC 2 Compliance

- [x] Access control (RBAC)
- [x] Audit logs
- [x] Encryption (in transit & at rest)
- [x] Change management (Git commits)
- [x] Incident response procedures

---

## Vulnerability Management

### Dependency Scanning

```bash
# Check for vulnerable dependencies
pip install safety
safety check

# Or: GitHub Dependabot scans automatically
# And creates PRs for updates
```

### Container Security

```bash
# Scan Docker image for vulnerabilities
docker scan itl/network-provider:0.1.0

# Use minimal base images
FROM python:3.12-slim

# Run as non-root
RUN useradd -m -u 1000 npuser
USER npuser
```

### Regular Security Audits

```bash
# Annual penetration testing
# Quarterly vulnerability scans
# Monthly dependency updates
```

---

## Operational Security

### Change Control

```bash
# All changes go through code review
# No direct production deployments
# Use GitOps workflow

# 1. Create feature branch
git checkout -b feature/add-resource

# 2. Commit changes
git commit -m "feat: add VNet resource"

# 3. Create pull request
#  Code review required
#  Tests must pass
#  Security scan must pass

# 4. Merge to main
#  GitHub Actions deploys automatically

# 5. Verification
#  Staging environment tested
#  Smoke tests run
#  Promoted to production
```

### Incident Response

```yaml
# Incident Response Plan
Severity 1 (Critical):
  - Network down / all clusters unreachable
  - Data breach / unauthorized access
  - Response time: 15 minutes
  - Escalation: CEO + Security Team

Severity 2 (High):
  - Single cluster down / degraded performance
  - Minor data inconsistency
  - Response time: 1 hour
  - Escalation: Engineering Lead

Severity 3 (Medium):
  - Non-critical feature broken
  - Performance degradation (not critical path)
  - Response time: 4 hours
  - Escalation: On-call engineer
```

---

## Best Practices Checklist

### Security 

- [x] Enable HTTPS/TLS everywhere
- [x] Use strong authentication (OIDC)
- [x] Implement RBAC
- [x] Audit all changes
- [x] Encrypt sensitive data
- [x] Regular penetration tests
- [x] Keep dependencies updated
- [x] Use network policies (Kubernetes)
- [x] Non-root container processes
- [x] Secrets in vault, not Git

### Availability 

- [x] Multi-cluster deployment
- [x] Database replication
- [x] Automated backups
- [x] Health checks
- [x] Monitoring & alerting
- [x] Graceful degradation
- [x] Load balancing
- [x] Rate limiting

### Compliance 

- [x] Audit logging
- [x] Data retention policies
- [x] GDPR-compliant
- [x] SOC 2 controls
- [x] Incident response plan
- [x] Change management
- [x] Documentation

---

## Next Steps

- **Deploy securely?**  [Production Deployment](PRODUCTION_DEPLOYMENT.md)
- **Monitor security?**  [Monitoring](../tasks/MONITORING.md)
- **Incident response?**  [Troubleshooting](../reference/TROUBLESHOOTING.md)

---

**Last Updated:** June 2026
