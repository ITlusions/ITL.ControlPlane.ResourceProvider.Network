# End-User Examples: Deploy Your First VNet

Real-world examples showing how end-users deploy infrastructure **without needing to know about Cilium, BGP, or Kubernetes internals**.

---

## Scenario: SaaS Company Deploying Production Infrastructure

**Goal:** Set up a production VNet with 3 subnets (frontend, backend, database), add firewall rules, and expose the API gateway to the internet.

**User Profile:** DevOps engineer who just signed up for ITL ControlPlane. No Kubernetes experience needed.

---

## Option 1: Web Portal (Easiest)

### Step 1: Create a Virtual Network

1. Log in to ITL Control Plane Portal  `https://controlplane.itlusions.com`
2. Click **Create Resource**  **Virtual Network**
3. Fill in:
   - **Name:** `prod-vnet`
   - **Subscription:** `Production` (already assigned to you)
   - **Address Space:** `10.0.0.0/16`
   - **Region:** `East US`
4. Click **Create**

**Portal shows:**
```
 Virtual Network created
  Name: prod-vnet
  Address Space: 10.0.0.0/16
  Status: Provisioned (2.3s)
  
  Next: Add subnets
```

---

### Step 2: Create Subnets

Portal  **prod-vnet**  **Subnets**  **+ Add Subnet**

| Subnet Name | CIDR | Purpose |
|---|---|---|
| `frontend` | `10.0.1.0/24` | Web servers, load balancer |
| `backend` | `10.0.2.0/24` | API servers, business logic |
| `database` | `10.0.3.0/24` | Databases (restricted access) |

**Portal shows:**
```
 Subnet "frontend" created (10.0.1.0/24)
 Subnet "backend" created (10.0.2.0/24)
 Subnet "database" created (10.0.3.0/24)

  Subnets: 3/5 (you can create 2 more)
```

---

### Step 3: Create Firewall Rules (NSGs)

Portal  **Create Resource**  **Network Security Group**

**Frontend NSG:**
```
Name: nsg-frontend

Inbound Rules:
   Allow HTTP (80) from 0.0.0.0/0
   Allow HTTPS (443) from 0.0.0.0/0

Outbound Rules:
   Allow all
```

**Backend NSG:**
```
Name: nsg-backend

Inbound Rules:
   Allow 8080 from nsg-frontend (talk to frontend)
   Allow 3306 from nsg-database (talk to database)

Outbound Rules:
   Allow all
```

**Database NSG:**
```
Name: nsg-database

Inbound Rules:
   Allow 3306 from nsg-backend (ONLY from backend)

Outbound Rules:
   Deny all (database doesn't need outbound)
```

**Portal shows:**
```
 NSG "nsg-frontend" created
 NSG "nsg-backend" created
 NSG "nsg-database" created

  Your infrastructure is protected!
```

---

### Step 4: Expose API Gateway to Internet

Portal  **Create Resource**  **Load Balancer**

```
Name: api-gateway-lb
VNet: prod-vnet
Subnet: frontend

Frontend Configuration:
   Public access (VLAN IP)
  
Backend Pool:
   Add your Kubernetes service

Health Check:
   HTTP /health (30s)
```

**Portal shows:**
```
 Load Balancer "api-gateway-lb" created

  External IP: 10.200.0.50
  Status: Ready
  
   Your API is now accessible at: http://10.200.0.50
```

---

## Option 2: CLI (itlc Command Line)

Same workflow, but via command line:

```bash
# 1. Create VNet
itlc vnet create \
  --name prod-vnet \
  --subscription prod \
  --address-space 10.0.0.0/16 \
  --region eastus

# Response:
#  VNet created: prod-vnet (10.0.0.0/16)
# 2.3 seconds

# 2. Create subnets
itlc subnet create \
  --vnet prod-vnet \
  --name frontend \
  --prefix 10.0.1.0/24

itlc subnet create \
  --vnet prod-vnet \
  --name backend \
  --prefix 10.0.2.0/24

itlc subnet create \
  --vnet prod-vnet \
  --name database \
  --prefix 10.0.3.0/24

# Response:
#  Subnet "frontend" created
#  Subnet "backend" created
#  Subnet "database" created

# 3. Create NSGs (firewall rules)
itlc nsg create \
  --name nsg-frontend \
  --inbound-rule "allow HTTP from 0.0.0.0/0 port 80" \
  --inbound-rule "allow HTTPS from 0.0.0.0/0 port 443"

itlc nsg create \
  --name nsg-backend \
  --inbound-rule "allow 8080 from nsg-frontend" \
  --inbound-rule "allow 3306 from nsg-database"

itlc nsg create \
  --name nsg-database \
  --inbound-rule "allow 3306 from nsg-backend" \
  --outbound-rule "deny all"

# Response:
#  NSG "nsg-frontend" created
#  NSG "nsg-backend" created
#  NSG "nsg-database" created

# 4. Create load balancer (expose to internet)
itlc lb create \
  --name api-gateway-lb \
  --vnet prod-vnet \
  --subnet frontend \
  --public \
  --backend-pool-name api-services \
  --health-check-path /health

# Response:
#  Load Balancer "api-gateway-lb" created
# 
# External IP: 10.200.0.50
# Status: Ready
```

---

## Option 3: Infrastructure as Code (Terraform)

Save as `main.tf` and run `terraform apply`:

```hcl
# Configure ITL Control Plane provider
terraform {
  required_providers {
    itl = {
      source = "itlusions/itl"
      version = "~> 2.0"
    }
  }
}

provider "itl" {
  endpoint   = "https://controlplane.itlusions.com"
  auth_token = var.itl_token  # Set via env or tfvars
}

# 1. Create Virtual Network
resource "itl_virtual_network" "prod" {
  name              = "prod-vnet"
  subscription_id   = var.subscription_id
  address_space     = ["10.0.0.0/16"]
  resource_group    = "prod-rg"
  location          = "eastus"

  tags = {
    environment = "production"
    team        = "platform"
  }
}

# 2. Create Subnets
resource "itl_subnet" "frontend" {
  name                = "frontend"
  virtual_network_id  = itl_virtual_network.prod.id
  address_prefix      = "10.0.1.0/24"
  service_endpoints   = ["Microsoft.Storage"]
}

resource "itl_subnet" "backend" {
  name                = "backend"
  virtual_network_id  = itl_virtual_network.prod.id
  address_prefix      = "10.0.2.0/24"
}

resource "itl_subnet" "database" {
  name                = "database"
  virtual_network_id  = itl_virtual_network.prod.id
  address_prefix      = "10.0.3.0/24"
}

# 3. Create Network Security Groups (Firewalls)
resource "itl_network_security_group" "frontend" {
  name                = "nsg-frontend"
  resource_group      = "prod-rg"
  subscription_id     = var.subscription_id

  security_rule {
    name                       = "allow-http"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "TCP"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-https"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "TCP"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "itl_network_security_group" "backend" {
  name                = "nsg-backend"
  resource_group      = "prod-rg"
  subscription_id     = var.subscription_id

  security_rule {
    name                       = "allow-from-frontend"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "TCP"
    source_port_range          = "*"
    destination_port_range     = "8080"
    source_address_prefix      = "10.0.1.0/24"  # From frontend subnet
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-from-database"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "TCP"
    source_port_range          = "*"
    destination_port_range     = "3306"
    source_address_prefix      = "10.0.3.0/24"  # From database subnet
    destination_address_prefix = "*"
  }
}

resource "itl_network_security_group" "database" {
  name                = "nsg-database"
  resource_group      = "prod-rg"
  subscription_id     = var.subscription_id

  security_rule {
    name                       = "allow-from-backend"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "TCP"
    source_port_range          = "*"
    destination_port_range     = "3306"
    source_address_prefix      = "10.0.2.0/24"  # From backend subnet
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "deny-all-outbound"
    priority                   = 4096
    direction                  = "Outbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

# 4. Create Load Balancer (expose API to internet)
resource "itl_load_balancer" "api" {
  name                = "api-gateway-lb"
  location            = "eastus"
  resource_group      = "prod-rg"
  subscription_id     = var.subscription_id
  public              = true  # Get VLAN IP

  frontend_ip_configuration {
    name                          = "public"
    subnet_id                     = itl_subnet.frontend.id
    private_ip_address_allocation = "Dynamic"
  }

  backend_address_pool {
    name = "api-services"
  }

  probe {
    name                = "health"
    protocol            = "Http"
    port                = 8080
    path                = "/health"
    interval_in_seconds = 30
  }

  load_balancing_rule {
    name                    = "api-rule"
    protocol                = "Tcp"
    frontend_port           = 443
    backend_port            = 8080
    frontend_ip_config_name = "public"
    backend_pool_name       = "api-services"
    probe_name              = "health"
  }

  tags = {
    environment = "production"
  }
}

# Output the public IP
output "api_gateway_ip" {
  value       = itl_load_balancer.api.frontend_public_ip
  description = "Public IP to access your API"
}
```

**Deploy:**
```bash
terraform init
terraform plan
terraform apply

# Output:
# Apply complete! Resources created: 7
# 
# api_gateway_ip = 10.200.0.50
#
#  Access your API at: http://10.200.0.50
```

---

## Option 4: Bicep (Azure-style IaC)

```bicep
// prod-infrastructure.bicep

param location string = 'eastus'
param vnetName string = 'prod-vnet'
param subscriptionId string

// Create VNet
resource vnet 'Microsoft.Network/virtualNetworks@2023-04-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.0.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'frontend'
        properties: {
          addressPrefix: '10.0.1.0/24'
          networkSecurityGroup: {
            id: nsgFrontend.id
          }
        }
      }
      {
        name: 'backend'
        properties: {
          addressPrefix: '10.0.2.0/24'
          networkSecurityGroup: {
            id: nsgBackend.id
          }
        }
      }
      {
        name: 'database'
        properties: {
          addressPrefix: '10.0.3.0/24'
          networkSecurityGroup: {
            id: nsgDatabase.id
          }
        }
      }
    ]
  }
}

// Frontend NSG
resource nsgFrontend 'Microsoft.Network/networkSecurityGroups@2023-04-01' = {
  name: 'nsg-frontend'
  location: location
  properties: {
    securityRules: [
      {
        name: 'allow-http'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'TCP'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'allow-https'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'TCP'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// Backend NSG
resource nsgBackend 'Microsoft.Network/networkSecurityGroups@2023-04-01' = {
  name: 'nsg-backend'
  location: location
  properties: {
    securityRules: [
      {
        name: 'allow-from-frontend'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'TCP'
          sourcePortRange: '*'
          destinationPortRange: '8080'
          sourceAddressPrefix: '10.0.1.0/24'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// Database NSG
resource nsgDatabase 'Microsoft.Network/networkSecurityGroups@2023-04-01' = {
  name: 'nsg-database'
  location: location
  properties: {
    securityRules: [
      {
        name: 'allow-from-backend'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'TCP'
          sourcePortRange: '*'
          destinationPortRange: '3306'
          sourceAddressPrefix: '10.0.2.0/24'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// Create Load Balancer
resource lb 'Microsoft.Network/loadBalancers@2023-04-01' = {
  name: 'api-gateway-lb'
  location: location
  properties: {
    frontendIPConfigurations: [
      {
        name: 'public'
        properties: {
          subnet: {
            id: '${vnet.id}/subnets/frontend'
          }
          privateIPAllocationMethod: 'Dynamic'
          publicIPAddress: {
            id: publicIP.id
          }
        }
      }
    ]
    backendAddressPools: [
      {
        name: 'api-services'
      }
    ]
    probes: [
      {
        name: 'health'
        properties: {
          protocol: 'Http'
          port: 8080
          requestPath: '/health'
          intervalInSeconds: 30
        }
      }
    ]
    loadBalancingRules: [
      {
        name: 'api-rule'
        properties: {
          frontendIPConfiguration: {
            id: '${lb.id}/frontendIPConfigurations/public'
          }
          backendAddressPool: {
            id: '${lb.id}/backendAddressPools/api-services'
          }
          probe: {
            id: '${lb.id}/probes/health'
          }
          protocol: 'Tcp'
          frontendPort: 443
          backendPort: 8080
        }
      }
    ]
  }
}

// Public IP for LB
resource publicIP 'Microsoft.Network/publicIPAddresses@2023-04-01' = {
  name: 'pip-api-gateway'
  location: location
  properties: {
    publicIPAddressVersion: 'IPv4'
    publicIPAllocationMethod: 'Dynamic'
  }
}

// Outputs
output vnetId string = vnet.id
output lbId string = lb.id
output apiGatewayIp string = publicIP.properties.ipAddress
```

**Deploy:**
```bash
az deployment group create \
  --resource-group prod-rg \
  --template-file prod-infrastructure.bicep \
  --parameters subscriptionId=$SUBSCRIPTION_ID
```

---

## Option 5: Pulumi (Python) - In Development 

**Status**: Network Provider team is implementing native components  
**Package**: `itl-controlplane-network-pulumi` (coming to PyPI)  
**ETA**: ~2 weeks  

### Coming Soon: Native Network Provider Components

The Network Provider team is building Pulumi components that will allow you to deploy everything as code:

```python
import pulumi
from itl_controlplane_network_pulumi import (
    VirtualNetwork, Subnet, NetworkSecurityGroup, LoadBalancer
)

# Create resources with full Python + Pulumi power
vnet = VirtualNetwork(
    'prod-vnet',
    address_space=['10.0.0.0/16'],
    location='westeurope',
    subscription_id='sub-00000001',
)

frontend = Subnet(
    'frontend',
    virtual_network_id=vnet.vnet_id,
    address_prefix='10.0.1.0/24'
)

nsg = NetworkSecurityGroup(
    'nsg-frontend',
    location='westeurope',
    security_rules=[
        {
            'name': 'allow-https',
            'priority': 100,
            'direction': 'Inbound',
            'access': 'Allow',
            'protocol': 'TCP',
            'destination_port_range': '443'
        }
    ]
)

lb = LoadBalancer(
    'api-gateway-lb',
    vnet_id=vnet.vnet_id,
    public=True
)

pulumi.export('api_gateway_ip', lb.frontend_ip)
```

Deploy when available:
```bash
pulumi up
```

**Setup (when released):**
```bash
pip install itl-controlplane-network-pulumi
pulumi new python
pulumi up
```

---

### In the Meantime: Use Terraform or Bicep

While the Network Provider team implements Pulumi components, use **Option 3 (Terraform)** or **Option 4 (Bicep)** which are ready today.

Or use the **Pulumi + HTTP API workaround** below:

### Interim: Pulumi + REST API Workaround

Use Pulumi to call the Network Provider REST API directly:

```python
#!/usr/bin/env python3
import pulumi
import json
import requests

config = pulumi.Config()
subscription_id = config.require('subscription_id')
token = config.require_secret('api_token')
api_url = 'https://controlplane.itlusions.com'

headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}

# Create VNet via REST API
vnet_response = requests.put(
    f'{api_url}/subscriptions/{subscription_id}/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/prod-vnet',
    headers=headers,
    json={
        'location': 'westeurope',
        'properties': {'addressSpace': ['10.0.0.0/16']}
    }
)

pulumi.export('vnet_id', vnet_response.json()['id'])
```

---

### Track Development

-  **Implementation Plan**: [PULUMI_DEVELOPMENT_GUIDE.md](../../PULUMI_DEVELOPMENT_GUIDE.md)
-  **GitHub Issue**: Coming soon
-  **Package**: `itl-controlplane-network-pulumi`
-  **Timeline**: ~2 weeks

---

## Comparison: Which Method Should You Use?

| Method | Best For | Skill Level | Speed | Language | Status |
|--------|----------|-------------|-------|----------|--------|
| **Portal** | First-time setup, learning | Beginner | Medium | Visual | [x] Ready |
| **CLI (itlc)** | Quick deploys, scripting | Intermediate | Fast | Bash/PowerShell | [x] Ready |
| **Terraform** | Team workflows, GitOps | Advanced | Very Fast | HCL | [x] Ready |
| **Bicep** | Azure-aligned orgs | Intermediate | Very Fast | Bicep | [x] Ready |
| **Pulumi** | Python developers, CI/CD | Advanced | Very Fast | Python |  In Dev (Network Team) |

---

## What Happens Behind the Scenes?

**You deploy:** A simple VNet with 3 subnets

**Automatically, you get:**
- [x] Kubernetes namespaces for isolation (one per subscription)
- [x] Cilium networking pools in all 3 clusters
- [x] Cilium network policies (translated from NSGs)
- [x] BGP route advertisements to your physical network
- [x] Multi-cluster synchronization
- [x] Audit logging and compliance tracking
- [x] DNS resolution and service discovery
- [x] HA failover across clusters

**But you don't need to manage any of this.** It just works!

---

## Next Steps

- Ready to scale?  [Multi-Subscription Peering](03-MULTI_SUBSCRIPTION.md)
- Need Kubernetes integration?  [K8s Deployment](../guides/users/KUBERNETES_USER.md)
- Managing via API?  [API User Guide](../guides/users/ITL_API_USER.md)

---

**Last Updated:** June 2026
