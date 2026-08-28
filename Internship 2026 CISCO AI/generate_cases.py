"""Generate a varied Cisco Packet Tracer troubleshooting dataset."""

import csv
import ipaddress
import random
from pathlib import Path


HEADERS = [
    "Symptom",
    "Topology Note",
    "Show Outputs",
    "Expected Fault",
    "OSI Layer",
    "Concept Tag",
    "Severity",
]


VLAN_POOLS = [
    ("31", "172.22.31.0/27"),
    ("47", "10.61.47.0/26"),
    ("63", "192.168.63.0/28"),
    ("88", "172.29.88.0/25"),
    ("112", "10.84.112.0/27"),
    ("141", "192.168.141.0/26"),
]


CASE_SPECS = [
    ("Inter-VLAN clients cannot reach the gateway", "router-on-a-stick", "subinterface encapsulation mismatch", "Layer 2", "inter-vlan-routing", "High"),
    ("Only one VLAN can reach remote networks", "router-on-a-stick", "trunk allows an incomplete VLAN list", "Layer 2", "inter-vlan-routing", "High"),
    ("Hosts in a new VLAN receive no inter-VLAN replies", "multilayer switch", "SVI is administratively down", "Layer 3", "inter-vlan-routing", "High"),
    ("Inter-VLAN pings fail after an addressing change", "multilayer switch", "SVI and host subnet masks disagree", "Layer 3", "inter-vlan-routing", "High"),
    ("One department cannot reach its server VLAN", "router-on-a-stick", "native VLAN mismatch causes tagged traffic loss", "Layer 2", "inter-vlan-routing", "Critical"),
    ("VLAN 141 users can reach local hosts but not the WAN", "multilayer switch", "ip routing is disabled on the switch", "Layer 3", "inter-vlan-routing", "High"),
    ("A routed VLAN works from the router but not from clients", "router-on-a-stick", "default gateway points at the wrong subinterface", "Layer 3", "inter-vlan-routing", "High"),
    ("New finance VLAN is isolated from every other VLAN", "multilayer switch", "SVI has an overlapping network", "Layer 3", "inter-vlan-routing", "Critical"),
    ("Clients intermittently lose access between VLANs", "multilayer switch", "duplicate HSRP virtual address", "Layer 3", "inter-vlan-routing", "High"),
    ("A trunked access block cannot reach the core VLAN", "router-on-a-stick", "switchport is left in access mode", "Layer 2", "inter-vlan-routing", "High"),
    ("New wireless clients report DHCP timeout", "central DHCP server", "scope has no free leases", "Layer 7", "dhcp-exhaustion", "High"),
    ("IoT devices stop receiving addresses while laptops work", "central DHCP server", "small IoT pool is exhausted", "Layer 7", "dhcp-exhaustion", "Medium"),
    ("A remote access switch gets APIPA addresses", "DHCP relay", "ip helper-address is absent", "Layer 3", "dhcp-exhaustion", "High"),
    ("Guest clients cannot renew leases", "central DHCP server", "excluded range consumes the entire guest pool", "Layer 7", "dhcp-exhaustion", "High"),
    ("Printers fail to join after a lab expansion", "central DHCP server", "lease database reached its allocation limit", "Layer 7", "dhcp-exhaustion", "Medium"),
    ("Voice handsets receive data VLAN addresses", "router-on-a-stick", "voice DHCP scope has no matching option", "Layer 7", "dhcp-exhaustion", "High"),
    ("A branch subnet has no usable DHCP addresses", "DHCP relay", "relay targets a decommissioned server", "Layer 3", "dhcp-exhaustion", "High"),
    ("Clients keep an old address after moving ports", "central DHCP server", "stale leases were not cleared", "Layer 7", "dhcp-exhaustion", "Medium"),
    ("A restricted lab fills its pool within minutes", "central DHCP server", "rogue clients consume the dynamic range", "Layer 2", "dhcp-exhaustion", "Critical"),
    ("DHCP works on one floor but not the other", "DHCP relay", "relay interface is in the wrong VRF", "Layer 3", "dhcp-exhaustion", "High"),
    ("Remote site has no route to the application subnet", "OSPF point-to-point WAN", "network statement omits the transit prefix", "Layer 3", "dynamic-routing", "High"),
    ("A static route never appears in the routing table", "dual-router edge", "next hop is not recursively reachable", "Layer 3", "static-routing", "High"),
    ("Users can browse internally but not outside the campus", "edge NAT router", "inside interface is marked as outside", "Layer 3", "nat", "Critical"),
    ("HTTPS to a server is denied while ping succeeds", "firewall-on-a-stick", "extended ACL has an overbroad deny", "Layer 3", "access-control", "High"),
    ("Only return traffic is missing on a routed link", "three-router chain", "ACL applied in the wrong direction", "Layer 3", "access-control", "High"),
    ("A serial link shows down/down", "legacy serial WAN", "DCE side has no clock rate", "Layer 1", "wan-encapsulation", "Critical"),
    ("Neighbors form but routes never exchange", "OSPF multi-area", "area IDs differ on the shared segment", "Layer 3", "dynamic-routing", "High"),
    ("The backup link is selected instead of fiber", "floating static routes", "primary administrative distance is too high", "Layer 3", "path-selection", "Medium"),
    ("Switch management becomes unreachable after a reload", "layer-2 management VLAN", "management SVI lacks an active access port", "Layer 2", "switch-management", "Medium"),
    ("A server is reachable by IP but not by name", "internal DNS segment", "DHCP hands out the wrong DNS server", "Layer 7", "name-resolution", "Medium"),
]


def _network_details(network_text):
    network = ipaddress.ip_network(network_text)
    hosts = list(network.hosts())
    return network, hosts


def _random_network(rng, pool):
    vlan_id, network_text = rng.choice(pool)
    network, hosts = _network_details(network_text)
    gateway = hosts[0]
    return vlan_id, network, hosts, gateway


def show_ip_interface_brief(rng, interfaces):
    """Render a compact, realistic IOS interface summary."""
    lines = ["Interface              IP-Address      OK? Method Status                Protocol"]
    lines.append("GigabitEthernet0/0     unassigned      YES unset  up                    up")
    for name, address, status, protocol in interfaces:
        lines.append(f"{name:<23}{address:<16}YES DHCP  {status:<23}{protocol}")
    return "\n".join(lines)


def show_ip_route(rng, networks, fault=None):
    """Render routes with varied administrative sources and one useful clue."""
    lines = ["Codes: C - connected, S - static, O - OSPF, D - EIGRP, * - candidate default"]
    for network_text, source in networks:
        network = ipaddress.ip_network(network_text)
        if source == "C":
            lines.append(f"C    {network.with_prefixlen} is directly connected, Vlan{network.network_address.packed[-1]}")
        else:
            next_hop = ipaddress.ip_address(int(network.network_address) + 1)
            lines.append(f"{source}    {network.with_prefixlen} [110/20] via {next_hop}, 00:04:12, GigabitEthernet0/1")
    if fault == "missing-default":
        lines.append("! No candidate default route is present")
    else:
        lines.append("S*   0.0.0.0/0 [1/0] via 10.19.240.1")
    return "\n".join(lines)


def show_access_lists(rng, acl_number, permit_service="ip", deny_service="tcp"):
    """Render an ACL with randomized counters that expose a troubleshooting clue."""
    permit_count = rng.randint(2, 38)
    deny_count = rng.randint(0, 4)
    return "\n".join(
        [
            f"Extended IP access list {acl_number}",
            f"    10 permit {permit_service} any any (hitcnt={permit_count})",
            f"    20 deny {deny_service} any any eq 443 (hitcnt={deny_count})",
            "    30 permit ip any any (hitcnt=0)",
        ]
    )


def _outputs_for(spec, rng):
    _, topology, fault, _, tag, _ = spec
    vlan_id, network, hosts, gateway = _random_network(rng, VLAN_POOLS)
    spare_vlan, spare_network, _, spare_gateway = _random_network(rng, VLAN_POOLS)
    interfaces = [
        ("GigabitEthernet0/1", str(gateway), "up", "up"),
        ("GigabitEthernet0/2", str(spare_gateway), "up", "up"),
        ("Vlan" + vlan_id, str(gateway), "up", "up"),
    ]
    if "inter-vlan-routing" in tag and "administratively" in fault:
        interfaces[-1] = ("Vlan" + vlan_id, str(gateway), "administratively down", "down")
    if tag == "dhcp-exhaustion":
        interfaces[1] = ("GigabitEthernet0/2", str(hosts[-1]), "up", "up")
    routes = [(str(network), "C"), (str(spare_network), "O")]
    route_fault = "missing-default" if tag == "dynamic-routing" else None
    return "\n\n".join(
        [
            "show ip interface brief\n" + show_ip_interface_brief(rng, interfaces),
            "show ip route\n" + show_ip_route(rng, routes, route_fault),
            "show access-lists\n" + show_access_lists(rng, 100 + int(vlan_id)),
        ]
    )


def build_cases(seed=20260827):
    rng = random.Random(seed)
    cases = []
    for symptom, topology, fault, layer, tag, severity in CASE_SPECS:
        cases.append(
            {
                "Symptom": symptom,
                "Topology Note": f"{topology}; VLANs are non-default and addressing is drawn from a private lab range.",
                "Show Outputs": _outputs_for((symptom, topology, fault, layer, tag, severity), rng),
                "Expected Fault": fault,
                "OSI Layer": layer,
                "Concept Tag": tag,
                "Severity": severity,
            }
        )
    assert len(cases) == 30
    assert len({tuple(case[header] for header in HEADERS) for case in cases}) == 30
    return cases


def write_cases(output_path=None, seed=20260827):
    output_path = Path(output_path or Path(__file__).with_name("cases.csv"))
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(build_cases(seed))
    return output_path


if __name__ == "__main__":
    destination = write_cases()
    print(f"Wrote 30 troubleshooting cases to {destination}")
