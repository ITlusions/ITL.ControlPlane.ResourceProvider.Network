#!/usr/bin/env python3
"""
Real-Time ARP Discovery Demo

Demonstrates the IP discovery functionality including:
1. Discovering active IPs via ARP
2. Listing pods in subnets
3. Comparing actual vs discovered IPs
4. Identifying orphaned resources

Run with: python demo_arp_discovery.py
"""

import asyncio
import json
from typing import Optional
from dataclasses import asdict

# In real usage, import from src
# from src.ip_management import IPManager, ActiveIP

# For demo purposes, we'll mock the IPManager


class MockIPManager:
    """Mock IP Manager for demonstration."""
    
    async def discover_arp_entries(self, subnet_cidr: str, namespace: Optional[str] = None):
        """Mock ARP discovery - returns simulated discovered IPs."""
        # Simulate ARP discovery on Cilium nodes
        # In reality, this queries actual ARP tables from nodes
        mock_arp_entries = [
            {
                "ip_address": "10.0.1.5",
                "mac_address": "52:54:00:12:34:56",
                "resource_type": "arp_discovery",
                "status": "active",
                "last_seen": "2026-06-05T12:34:56.789Z"
            },
            {
                "ip_address": "10.0.1.10",
                "mac_address": "52:54:00:ab:cd:ef",
                "resource_type": "arp_discovery",
                "status": "active",
                "last_seen": "2026-06-05T12:34:50.123Z"
            },
            {
                "ip_address": "10.0.1.15",
                "mac_address": "52:54:00:11:22:33",
                "resource_type": "arp_discovery",
                "status": "active",
                "last_seen": "2026-06-05T12:34:45.456Z"
            },
            {
                "ip_address": "10.0.1.20",
                "mac_address": "52:54:00:44:55:66",
                "resource_type": "arp_discovery",
                "status": "active",
                "last_seen": "2026-06-05T12:34:40.789Z"
            },
            {
                "ip_address": "10.0.1.25",
                "mac_address": "52:54:00:77:88:99",
                "resource_type": "arp_discovery",
                "status": "active",
                "last_seen": "2026-06-05T12:34:35.012Z"
            },
        ]
        return mock_arp_entries
    
    async def list_active_ips_in_subnet(self, vnet_name: str, subnet_name: str, namespace: Optional[str] = None):
        """Mock active IPs in subnet - returns simulated pod IPs."""
        mock_active_ips = [
            {
                "ip_address": "10.0.1.5",
                "subnet_cidr": "10.0.1.0/24",
                "resource_type": "pod",
                "resource_name": "api-server-7d8f9c2a",
                "namespace": "sub-00000001",
                "pod_name": "api-server-7d8f9c2a",
                "node_name": "node-1",
                "status": "active",
                "last_seen": "2026-06-05T12:34:56.789Z"
            },
            {
                "ip_address": "10.0.1.10",
                "subnet_cidr": "10.0.1.0/24",
                "resource_type": "pod",
                "resource_name": "cache-worker-a3b2c1d0",
                "namespace": "sub-00000001",
                "pod_name": "cache-worker-a3b2c1d0",
                "node_name": "node-2",
                "status": "active",
                "last_seen": "2026-06-05T12:34:50.123Z"
            },
            {
                "ip_address": "10.0.1.15",
                "subnet_cidr": "10.0.1.0/24",
                "resource_type": "pod",
                "resource_name": "db-connector-f7e9d2c3",
                "namespace": "sub-00000001",
                "pod_name": "db-connector-f7e9d2c3",
                "node_name": "node-3",
                "status": "active",
                "last_seen": "2026-06-05T12:34:45.456Z"
            },
            # 10.0.1.20 is in ARP but NOT in pods - ORPHANED!
            # 10.0.1.25 is in ARP but NOT in pods - ORPHANED!
        ]
        return mock_active_ips


async def demo_basic_arp_discovery():
    """Demo 1: Basic ARP Discovery"""
    print("\n" + "="*80)
    print("DEMO 1: BASIC ARP DISCOVERY")
    print("="*80)
    print("\nScanning 10.0.1.0/24 subnet for active IPs via ARP...\n")
    
    manager = MockIPManager()
    discovered = await manager.discover_arp_entries("10.0.1.0/24")
    
    print(f"✓ Discovered {len(discovered)} active IPs via ARP\n")
    print("IP Address   | MAC Address         | Status | Last Seen")
    print("-" * 70)
    for ip in discovered:
        print(f"{ip['ip_address']:<12} | {ip['mac_address']:<19} | {ip['status']:<6} | {ip['last_seen']}")
    
    return discovered


async def demo_compare_arp_vs_pods():
    """Demo 2: Compare ARP Discovery vs Actual Pods"""
    print("\n" + "="*80)
    print("DEMO 2: ARP DISCOVERY vs KUBERNETES PODS (Orphan Detection)")
    print("="*80)
    
    manager = MockIPManager()
    
    # Get ARP entries
    print("\n[1/2] Querying ARP from Cilium nodes...")
    arp_entries = await manager.discover_arp_entries("10.0.1.0/24")
    arp_ips = {entry['ip_address'] for entry in arp_entries}
    print(f"✓ Found {len(arp_ips)} IPs via ARP: {sorted(arp_ips)}")
    
    # Get actual pod IPs
    print("\n[2/2] Querying Kubernetes pod IPs...")
    pod_ips = await manager.list_active_ips_in_subnet("prod-vnet", "prod-subnet")
    pod_ip_set = {pod['ip_address'] for pod in pod_ips}
    print(f"✓ Found {len(pod_ip_set)} pod IPs: {sorted(pod_ip_set)}")
    
    # Analyze differences
    print("\n" + "-"*70)
    print("ANALYSIS:")
    print("-"*70)
    
    orphaned_ips = arp_ips - pod_ip_set
    missing_ips = pod_ip_set - arp_ips
    active_ips = arp_ips & pod_ip_set
    
    print(f"\n✓ Active (in both ARP + Kubernetes): {len(active_ips)} IPs")
    for ip in sorted(active_ips):
        pod = next((p for p in pod_ips if p['ip_address'] == ip), None)
        print(f"  • {ip} → Pod: {pod['pod_name']} on {pod['node_name']}")
    
    if orphaned_ips:
        print(f"\n⚠ ORPHANED (in ARP but NOT in Kubernetes): {len(orphaned_ips)} IPs")
        print("  These IPs are responding on network but have no pod running!")
        for ip in sorted(orphaned_ips):
            arp = next((a for a in arp_entries if a['ip_address'] == ip), None)
            print(f"  • {ip} (MAC: {arp['mac_address']}) - Last seen: {arp['last_seen']}")
            print(f"    → Action: Check if pod crashed, or clean up stuck network interface")
    
    if missing_ips:
        print(f"\n⚠ UNREACHABLE (in Kubernetes but NOT in ARP): {len(missing_ips)} IPs")
        print("  These pods are running but not responding to ARP!")
        for ip in sorted(missing_ips):
            pod = next((p for p in pod_ips if p['ip_address'] == ip), None)
            print(f"  • {ip} → Pod: {pod['pod_name']}")
            print(f"    → Action: Check pod network interface, restart pod if needed")
    
    return {
        "total_arp": len(arp_ips),
        "total_pods": len(pod_ip_set),
        "active": len(active_ips),
        "orphaned": len(orphaned_ips),
        "unreachable": len(missing_ips)
    }


async def demo_realtime_monitoring():
    """Demo 3: Real-Time Monitoring Simulation"""
    print("\n" + "="*80)
    print("DEMO 3: REAL-TIME MONITORING (Simulated)")
    print("="*80)
    print("\nSimulating continuous monitoring of subnet activity...\n")
    
    manager = MockIPManager()
    
    # Simulate 3 time intervals
    for interval in range(1, 4):
        print(f"\n--- Scan #{interval} ---")
        discovered = await manager.discover_arp_entries("10.0.1.0/24")
        active_count = len(discovered)
        
        # Simulate IP changes
        if interval == 1:
            print(f"[{interval}] Found {active_count} active IPs")
        elif interval == 2:
            print(f"[{interval}] Found {active_count} active IPs (↑ NEW IP detected: 10.0.1.30)")
            discovered_copy = discovered.copy()
            discovered_copy.append({
                "ip_address": "10.0.1.30",
                "mac_address": "52:54:00:aa:bb:cc",
                "resource_type": "arp_discovery",
                "status": "active",
                "last_seen": "2026-06-05T12:35:10.111Z"
            })
            active_count = len(discovered_copy)
        else:
            print(f"[{interval}] Found {active_count} active IPs (↓ IP 10.0.1.20 went silent)")
        
        # Detailed list
        print(f"\nActive IPs:")
        for ip in sorted(discovered, key=lambda x: x['ip_address']):
            print(f"  • {ip['ip_address']} ({ip['mac_address']}) - Last seen: {ip['last_seen']}")
        
        # Status
        if interval < 3:
            print("\n(Waiting 30 seconds for next scan...)")


async def demo_tenant_filtering():
    """Demo 4: Multi-Tenant ARP Filtering"""
    print("\n" + "="*80)
    print("DEMO 4: MULTI-TENANT NETWORK ISOLATION")
    print("="*80)
    
    manager = MockIPManager()
    
    print("\nScenario: Two tenants sharing VLAN 100 (10.200.0.0/24)")
    print("But isolated by Cilium network policies in separate namespaces\n")
    
    # Tenant A
    print("Tenant A (sub-00000001):")
    print("  VLAN IP Pool: 10.200.0.0/24")
    arp_a = await manager.discover_arp_entries("10.200.0.0/24", namespace="sub-00000001")
    print(f"  Active IPs: {[entry['ip_address'] for entry in arp_a]}")
    
    # Tenant B
    print("\nTenant B (sub-00000002):")
    print("  VLAN IP Pool: 10.200.0.0/24 (SAME CIDR!)")
    arp_b = await manager.discover_arp_entries("10.200.0.0/24", namespace="sub-00000002")
    print(f"  Active IPs: {[entry['ip_address'] for entry in arp_b]}")
    
    print("\n✓ Both tenants can use same CIDR - isolated by Cilium policies!")
    print("✓ No IP conflicts because NetworkPolicy blocks cross-tenant traffic")


async def demo_json_output():
    """Demo 5: JSON API Response Format"""
    print("\n" + "="*80)
    print("DEMO 5: JSON API RESPONSE FORMAT")
    print("="*80)
    print("\nREST API: GET /api/v1/network/arp-discovery?subnet_cidr=10.0.1.0/24\n")
    
    manager = MockIPManager()
    discovered = await manager.discover_arp_entries("10.0.1.0/24")
    
    # Format as API response
    response = {
        "subnet_cidr": "10.0.1.0/24",
        "discovered_ips": discovered,
        "total_discovered": len(discovered),
        "timestamp": "2026-06-05T12:35:00.000Z",
        "scan_duration_ms": 1234
    }
    
    print(json.dumps(response, indent=2))


async def main():
    """Run all demos."""
    print("\n" + "╔" + "="*78 + "╗")
    print("║" + " "*20 + "REAL-TIME ARP DISCOVERY DEMO" + " "*30 + "║")
    print("╚" + "="*78 + "╝")
    
    try:
        # Run demos
        await demo_basic_arp_discovery()
        await demo_compare_arp_vs_pods()
        await demo_realtime_monitoring()
        await demo_tenant_filtering()
        await demo_json_output()
        
        # Summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print("""
The Real-Time ARP Discovery feature enables:

✓ Active IP Detection      - Find all IPs responding on network via ARP
✓ Orphan Detection         - Identify pods that crashed but left network artifacts
✓ Unreachable Detection    - Find pods running but not responding to ARP
✓ Multi-Tenant Isolation   - Verify Cilium policies isolate tenants correctly
✓ Real-Time Monitoring     - Continuous scanning for capacity planning
✓ JSON API Integration     - Easy integration with monitoring/alerting systems

Use Cases:
  • Capacity planning: "How many IPs are actually in use?"
  • Debugging: "Why can't I reach this IP?"
  • Automation: Alert when utilization > 80%
  • Security: Detect unauthorized network activity
  • Scaling: Determine when to add new subnets

Performance:
  • Single subnet scan: 1-5 seconds (queries all Cilium nodes)
  • Supported subnets: /24 or larger (sufficient for typical clusters)
  • Frequency: Run every 30-60 seconds for real-time monitoring
""")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
