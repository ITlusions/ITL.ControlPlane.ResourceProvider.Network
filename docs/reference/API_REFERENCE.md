# API Reference

## Base URL

```
http://localhost:8002
```

## Port

The Network Provider runs on **port 8002** by default.

---

## Resource Types

All resources follow ARM-style paths:

```
/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/{resourceType}/{resourceName}
```

---

## Virtual Networks

### Create VNet

**Request:**
```
POST /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualNetworks/{vnetName}

Content-Type: application/json
Authorization: Bearer {token}

{
    "location": "eastus",
    "properties": {
        "addressSpace": ["10.0.0.0/16"]
    }
}
```

**Response (201 Created):**
```json
{
    "id": "/subscriptions/sub-00000001/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/vnet-prod",
    "name": "vnet-prod",
    "type": "Microsoft.Network/virtualNetworks",
    "properties": {
        "addressSpace": ["10.0.0.0/16"],
        "subnets": [],
        "provisioningState": "Succeeded"
    }
}
```

### Get VNet

```
GET /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualNetworks/{vnetName}
```

**Response (200 OK):** Full VNet object

### Update VNet

```
PATCH /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualNetworks/{vnetName}

{
    "properties": {
        "addressSpace": ["10.0.0.0/16", "10.1.0.0/16"]
    }
}
```

### Delete VNet

```
DELETE /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualNetworks/{vnetName}
```

**Response (204 No Content)**

---

## Subnets

### Create Subnet

```
POST /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualNetworks/{vnetName}/subnets/{subnetName}

{
    "properties": {
        "addressPrefix": "10.0.1.0/24"
    }
}
```

### Get Subnet

```
GET /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualNetworks/{vnetName}/subnets/{subnetName}
```

### Delete Subnet

```
DELETE /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualNetworks/{vnetName}/subnets/{subnetName}
```

---

## Network Security Groups (NSGs)

### Create NSG

```
POST /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/networkSecurityGroups/{nsgName}

{
    "location": "eastus",
    "properties": {
        "securityRules": [
            {
                "name": "allow-http",
                "properties": {
                    "access": "Allow",
                    "direction": "Inbound",
                    "priority": 100,
                    "protocol": "TCP",
                    "destinationPortRange": "80",
                    "sourceAddressPrefix": "*",
                    "destinationAddressPrefix": "*"
                }
            }
        ]
    }
}
```

### Security Rule Properties

| Property | Type | Description |
|---|---|---|
| `name` | string | Rule name |
| `access` | Allow, Deny | Action |
| `direction` | Inbound, Outbound | Direction |
| `priority` | int (100-4096) | Processing order |
| `protocol` | TCP, UDP, *, Icmp | Protocol |
| `sourcePortRange` | int, range, * | Source port(s) |
| `destinationPortRange` | int, range, * | Dest port(s) |

---

## Virtual Network Peering

### Create VNet Peering

```
POST /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualNetworks/{vnetName}/virtualNetworkPeerings/{peeringName}

{
    "properties": {
        "remoteVirtualNetwork": {
            "id": "/subscriptions/{remoteSubscriptionId}/resourceGroups/{remoteRg}/providers/Microsoft.Network/virtualNetworks/{remoteVnetName}"
        },
        "allowVirtualNetworkAccess": true,
        "allowForwardedTraffic": false
    }
}
```

### Delete VNet Peering

```
DELETE /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Network/virtualNetworks/{vnetName}/virtualNetworkPeerings/{peeringName}
```

---

**Last Updated:** June 2026
