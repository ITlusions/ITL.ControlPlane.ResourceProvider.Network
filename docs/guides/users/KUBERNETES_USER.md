# For Kubernetes Users: LoadBalancer Services & External Access

Practical guide for developers and application owners to expose their services with direct VLAN IP addresses using Kubernetes LoadBalancer services.

---

## Overview for K8s Users

Once your DevOps team has set up BGP peering and VLAN pools (see [../../operations/BGP_VLAN_SETUP.md](../../operations/BGP_VLAN_SETUP.md)), you can expose your applications directly to your physical network without any special configuration.

**Quick Example:**

```bash
# 1. Create a deployment
kubectl create deployment myapp --image=myapp:1.0

# 2. Expose it as LoadBalancer
kubectl expose deployment myapp --port=80 --target-port=8080 --type=LoadBalancer --labels=expose=external

# 3. Check the external IP
kubectl get svc myapp
# NAME    TYPE           CLUSTER-IP    EXTERNAL-IP       PORT(S)
# myapp   LoadBalancer   10.0.50.10    10.200.0.25       80:31234/TCP
#                                      
#                        Direct VLAN IP - ready to use!

# 4. Access from your network
curl http://10.200.0.25
# Direct connection, no additional routing needed!
```

---

## For Developers

### 1. Create Your Application

```yaml
# app.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-api
  namespace: prod-apps
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web-api
      tier: frontend
  template:
    metadata:
      labels:
        app: web-api
        tier: frontend
    spec:
      containers:
        - name: api
          image: mycompany/web-api:2.5.1
          ports:
            - containerPort: 8080
              name: http
          env:
            - name: PORT
              value: "8080"
            - name: LOG_LEVEL
              value: "info"
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
```

### 2. Expose as LoadBalancer Service

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: web-api
  namespace: prod-apps
  labels:
    app: web-api
    expose: external        #  KEY: Tells Cilium to assign external IP
  annotations:
    description: "Production Web API - Public endpoint"
    environment: "production"
spec:
  type: LoadBalancer        #  Creates a service with external IP
  selector:
    app: web-api
    tier: frontend
  ports:
    - name: http
      protocol: TCP
      port: 80              # External port
      targetPort: 8080      # Internal container port
    - name: https
      protocol: TCP
      port: 443
      targetPort: 8443
```

### 3. Deploy

```bash
# Create namespace
kubectl create namespace prod-apps

# Deploy application
kubectl apply -f app.yaml -n prod-apps
kubectl apply -f service.yaml -n prod-apps

# Check status
kubectl get deployment -n prod-apps
kubectl get svc -n prod-apps
```

### 4. Get Your External IP

```bash
# Watch for external IP assignment
kubectl get svc web-api -n prod-apps -w

# Output (after a few seconds):
# NAME      TYPE           CLUSTER-IP      EXTERNAL-IP     PORT(S)
# web-api   LoadBalancer   10.0.50.5       10.200.0.50     80:32000/TCP,443:32443/TCP
#                                          
#                           Your VLAN IP - directly routable!
```

### 5. Test Access

```bash
# From anywhere on your network
curl http://10.200.0.50
# Should get 200 OK

# Test with headers
curl -v http://10.200.0.50/api/users
curl -H "Authorization: Bearer token123" http://10.200.0.50/api/data

# DNS (if configured)
curl http://web-api.example.com
```

---

## For Operations Teams

### Monitoring & Health Checks

#### 1. Check Service Status

```bash
# View service details
kubectl describe svc web-api -n prod-apps

# Output:
# Name:                     web-api
# Namespace:                prod-apps
# Labels:                   app=web-api
#                          expose=external
# Annotations:              description: Production Web API
# Selector:                 app=web-api,tier=frontend
# Type:                     LoadBalancer
# IP:                       10.0.50.5
# LoadBalancer Ingress:     10.200.0.50      #  Your VLAN IP
# Port:                     http  80/TCP
# TargetPort:               8080/TCP
# NodePort:                 32000/TCP
# Endpoints:                10.0.1.50:8080,10.0.1.75:8080,10.0.1.99:8080
# Session Affinity:         None
# External Traffic Policy:  Cluster
# Events:                   <none>
```

#### 2. Check Endpoint Health

```bash
# View endpoints (backends receiving traffic)
kubectl get endpoints web-api -n prod-apps -o wide

# Output:
# NAME      ENDPOINTS                                                    AGE
# web-api   10.0.1.50:8080,10.0.1.75:8080,10.0.1.99:8080               2m

# If you see fewer endpoints than replicas, some pods aren't ready
kubectl get pods -n prod-apps -l app=web-api

# NAME                        READY   STATUS    RESTARTS   AGE
# web-api-5d4c7b8c9f-abc12    1/1     Running   0          2m
# web-api-5d4c7b8c9f-def45    1/1     Running   0          2m
# web-api-5d4c7b8c9f-ghi67    1/1     Running   0          2m
```

#### 3. Monitor Traffic

```bash
# View how traffic is distributed
kubectl logs -f pod/web-api-5d4c7b8c9f-abc12 -n prod-apps

# Or use a monitoring pod
kubectl run debug --image=curlimages/curl -it -- /bin/sh
# Inside: for i in {1..100}; do curl http://10.200.0.50/api/users; done
```

### Scaling

```bash
# Increase replicas
kubectl scale deployment web-api -n prod-apps --replicas=5

# Traffic automatically distributed to new pods
# External IP (10.200.0.50) remains the same

# Check new pods are healthy
kubectl get pods -n prod-apps -l app=web-api
```

### Updates & Rolling Deployment

```bash
# Update image (automatic rolling deployment)
kubectl set image deployment/web-api \
  api=mycompany/web-api:2.5.2 \
  -n prod-apps

# Monitor rollout
kubectl rollout status deployment/web-api -n prod-apps

# No change to external IP - seamless for users!
```

---

## Real-World Scenarios

### Scenario 1: Database Service

**Setup:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: database
  namespace: prod-apps
  labels:
    app: postgres
    expose: external      # Expose to network
spec:
  type: LoadBalancer
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
```

**Result:**
```bash
kubectl get svc database -n prod-apps
# NAME       TYPE           CLUSTER-IP    EXTERNAL-IP
# database   LoadBalancer   10.0.50.20    10.200.0.30
```

**Access from external application:**
```python
import psycopg2

conn = psycopg2.connect(
    host="10.200.0.30",      # Your VLAN IP!
    port=5432,
    user="dbuser",
    password="secure-pass",
    database="myapp"
)
```

---

### Scenario 2: Message Queue

**Setup:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: kafka
  namespace: prod-apps
  labels:
    app: kafka
    expose: external
spec:
  type: LoadBalancer
  selector:
    app: kafka
  ports:
    - name: broker
      port: 9092
      targetPort: 9092
    - name: zookeeper
      port: 2181
      targetPort: 2181
```

**Result:**
```bash
# Producer config
bootstrap.servers=10.200.0.40:9092    # Direct VLAN IP

# Consumer config
bootstrap.servers=10.200.0.40:9092    # Same VLAN IP
```

---

### Scenario 3: API Gateway

**Setup:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: gateway
  template:
    metadata:
      labels:
        app: gateway
    spec:
      containers:
        - name: gateway
          image: kong:3.0
          ports:
            - containerPort: 8000

---
apiVersion: v1
kind: Service
metadata:
  name: api-gateway
  labels:
    expose: external
spec:
  type: LoadBalancer
  selector:
    app: gateway
  ports:
    - port: 80
      targetPort: 8000
    - port: 443
      targetPort: 8443
```

**Result:**
```bash
kubectl get svc api-gateway
# NAME          TYPE           CLUSTER-IP    EXTERNAL-IP
# api-gateway   LoadBalancer   10.0.50.60    10.200.0.45

# Users access: http://10.200.0.45
# Or with DNS: http://gateway.yourcompany.com (resolve to 10.200.0.45)
```

---

## DNS Integration

### Option A: Manual DNS Record

```dns
; In your DNS zone file
api.prod                IN A    10.200.0.50    # Storage cluster
database.prod           IN A    10.200.0.30    # Storage cluster
kafka.prod              IN A    10.200.0.40    # Data cluster
gateway.prod            IN A    10.201.0.45    # Data cluster (different cluster!)
```

### Option B: Automated (ExternalDNS)

```yaml
# Install ExternalDNS to automatically create DNS records
apiVersion: v1
kind: ConfigMap
metadata:
  name: externaldns
  namespace: kube-system
data:
  config.yaml: |
    registry: txt
    provider: route53  # or azure, google, etc.
    policy: sync
    txtOwnerId: itl-storage-cluster
```

Result: Service IP 10.200.0.50 automatically gets DNS name!

---

## Multi-Cluster Services

### Share Service Across Clusters

If you want the same service available from all 3 clusters:

#### Storage Cluster (VLAN 100)
```bash
kubectl get svc api-gateway -n prod-apps
# EXTERNAL-IP: 10.200.0.50
```

#### Data Cluster (VLAN 200)
```bash
kubectl get svc api-gateway -n prod-apps
# EXTERNAL-IP: 10.201.0.50
```

#### Compute Cluster (VLAN 300)
```bash
kubectl get svc api-gateway -n prod-apps
# EXTERNAL-IP: 10.202.0.50
```

**User Experience:**
```bash
# All three IPs route to the same service (via ClusterMesh)
curl http://10.200.0.50    # Works
curl http://10.201.0.50    # Works
curl http://10.202.0.50    # Works

# Or with DNS round-robin
api.prod -> 10.200.0.50, 10.201.0.50, 10.202.0.50
```

---

## Troubleshooting for Users

### Service Has No External IP

**Symptom:**
```bash
kubectl get svc myapp
# NAME    TYPE           CLUSTER-IP    EXTERNAL-IP
# myapp   LoadBalancer   10.0.50.10    <pending>
```

**Causes & Fixes:**

1. **Missing label**  Service needs `expose: external` label

```bash
# Add label
kubectl patch svc myapp -p '{"metadata":{"labels":{"expose":"external"}}}'

# Or recreate with label
kubectl delete svc myapp
kubectl expose deployment myapp --type=LoadBalancer --labels=expose=external
```

2. **No IP pool available**  All IPs allocated

```bash
# Check IP pool status
kubectl describe ciliumloadbalancerippools -A

# If full, ask DevOps to expand pool:
# Edit CiliumLoadBalancerIPPool and increase CIDR range
```

3. **Cilium not ready**  Pods still initializing

```bash
# Check Cilium status
kubectl get pods -n kube-system -l k8s-app=cilium

# If not all Running, wait or restart:
kubectl delete pod -n kube-system -l k8s-app=cilium
```

### External IP Not Reachable

**Symptom:**
```bash
# Service has external IP but can't reach it
curl 10.200.0.50
# curl: (7) Failed to connect
```

**Fixes:**

1. **Check endpoints are healthy:**

```bash
kubectl get endpoints myapp -o wide
# Should show at least one IP
```

2. **Check pod logs:**

```bash
kubectl logs pod/myapp-xyz -n prod-apps
# Look for errors
```

3. **Test from inside cluster:**

```bash
# Pod-to-service connectivity works?
kubectl run debug --image=curlimages/curl -it -- curl http://myapp
```

4. **Network connectivity:**

```bash
# From your router/network:
ping 10.200.0.50
# Should get response

# Check route exists:
# (on router) show ip route | grep 10.200.0.0
```

---

## CLI Commands Reference

### Create & Manage Services

```bash
# Create service from deployment
kubectl expose deployment myapp --port=80 --target-port=8080 --type=LoadBalancer

# View services
kubectl get svc -A

# Describe service details
kubectl describe svc myapp -n prod-apps

# Edit service
kubectl edit svc myapp -n prod-apps

# Delete service
kubectl delete svc myapp -n prod-apps
```

### Monitor & Debug

```bash
# Watch service for IP assignment
kubectl get svc myapp -w

# View service endpoints
kubectl get endpoints myapp -o wide

# Pod logs
kubectl logs deployment/myapp -n prod-apps

# Execute command in pod
kubectl exec deployment/myapp -it -- /bin/sh

# Port forward (for local testing)
kubectl port-forward svc/myapp 8080:80 -n prod-apps
# Then: curl localhost:8080
```

### Labels & Filtering

```bash
# Show services with expose=external label
kubectl get svc -A -L expose

# Find services by label
kubectl get svc -A -l expose=external

# Filter to namespace
kubectl get svc -n prod-apps -l expose=external
```

---

## Best Practices

### Best Practices:

#### DO:

- [x] Use descriptive service names (`api-gateway`, `database`, not `service1`)
- [x] Add labels for organization (`expose=external`, `tier=backend`)
- [x] Use health checks (livenessProbe, readinessProbe)
- [x] Set resource requests/limits
- [x] Use multiple replicas for HA
- [x] Monitor your services regularly

### [-] DON'T:

- [-] Use default namespace for production services
- [-] Forget to add `expose: external` label
- [-] Use hardcoded pod IPs in configurations
- [-] Deploy single replicas for critical services
- [-] Assume external IPs are static (they can change if service recreated)

---

## Performance Expectations

### Typical Metrics

| Metric | Expected Value |
|---|---|
| IP Assignment Time | 5-10 seconds |
| BGP Route Advertisement | 2-5 seconds |
| Traffic Failover (node down) | < 30 seconds |
| Connection Latency | < 2ms (local network) |
| Throughput | Line rate (no artificial limits) |

### Example Latency Test

```bash
# From external machine
ping 10.200.0.50
# PING 10.200.0.50 (10.200.0.50) 56(84) bytes of data.
# 64 bytes from 10.200.0.50: icmp_seq=1 ttl=62 time=1.23 ms

# Throughput test
iperf3 -c 10.200.0.50
# [  5]  0.0-10.0 sec  1.25 GBytes  1.07 Gbps
```

---

## Getting Help

**For Application Issues:**
- Check pod logs: `kubectl logs deployment/myapp`
- Describe resources: `kubectl describe svc myapp`
- Check endpoints: `kubectl get endpoints myapp -o wide`

**For Network Issues:**
- Contact DevOps team
- Reference [../TROUBLESHOOTING.md](../TROUBLESHOOTING.md)
- Provide:
  - Service name and namespace
  - External IP (if assigned)
  - Pod logs
  - Network connectivity test results

**Documentation:**
- [../../operations/BGP_VLAN_SETUP.md](../../operations/BGP_VLAN_SETUP.md)  Infrastructure setup
- [../../technical/ARCHITECTURE.md](../../technical/ARCHITECTURE.md)  How everything works
- [../CONFIGURATION.md](../CONFIGURATION.md)  System configuration
