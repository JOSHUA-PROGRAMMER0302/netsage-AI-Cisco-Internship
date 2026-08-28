"""Deterministic checks for common Cisco configuration mistakes."""

import ipaddress
import re
from collections import defaultdict
from collections.abc import Mapping


class NetworkRuleChecker:
    """Parse simulated Cisco show output and report basic configuration errors."""

    _IP = r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3})"
    _MASK = r"(?P<mask>(?:\d{1,3}\.){3}\d{1,3})"
    _INTERFACE_LINE = re.compile(
        rf"^(?P<interface>\S+)\s+{_IP}\s+(?:YES|NO)\s+\S+\s+"
        rf"(?P<status>administratively down|down|up)\s+(?P<protocol>down|up)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    _CONFIG_ADDRESS = re.compile(
        rf"^\s*ip\s+address\s+{_IP}\s+{_MASK}(?:\s|$)",
        re.MULTILINE | re.IGNORECASE,
    )
    _DEFAULT_GATEWAY = re.compile(
        rf"^\s*ip\s+default-gateway\s+{_IP}\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    _ROUTE = re.compile(
        r"^\s*[A-Z*]?(?:\s+[A-Z*])?\s*(?P<network>\d{1,3}(?:\.\d{1,3}){3})/(?P<prefix>\d{1,2})\b",
        re.MULTILINE,
    )

    @staticmethod
    def _text(value):
        return value if isinstance(value, str) else ""

    @staticmethod
    def _address(value):
        try:
            return ipaddress.ip_address(value)
        except ValueError:
            return None

    @staticmethod
    def _network(address, mask):
        try:
            return ipaddress.ip_network(f"{address}/{mask}", strict=False)
        except ValueError:
            return None

    def parse_interface_brief(self, output):
        """Return interface records from ``show ip interface brief`` output."""
        records = []
        for match in self._INTERFACE_LINE.finditer(self._text(output)):
            address = self._address(match.group("ip"))
            if address is None:
                continue
            records.append(
                {
                    "interface": match.group("interface"),
                    "ip": str(address),
                    "status": match.group("status").lower(),
                    "protocol": match.group("protocol").lower(),
                }
            )
        return records

    def parse_interface_addresses(self, configuration):
        """Return valid ``ip address ADDRESS MASK`` pairs from interface config."""
        addresses = []
        for match in self._CONFIG_ADDRESS.finditer(self._text(configuration)):
            address = self._address(match.group("ip"))
            network = self._network(match.group("ip"), match.group("mask"))
            if address is not None and network is not None:
                addresses.append(
                    {"ip": str(address), "mask": match.group("mask"), "network": network}
                )
        return addresses

    def parse_default_gateway(self, configuration):
        """Return the configured default gateway, or ``None`` if absent/invalid."""
        match = self._DEFAULT_GATEWAY.search(self._text(configuration))
        if not match:
            return None
        address = self._address(match.group("ip"))
        return str(address) if address is not None else None

    def parse_routes(self, output):
        """Return valid destination networks from ``show ip route`` output."""
        routes = []
        for match in self._ROUTE.finditer(self._text(output)):
            try:
                routes.append(
                    ipaddress.ip_network(
                        f"{match.group('network')}/{match.group('prefix')}", strict=False
                    )
                )
            except ValueError:
                continue
        return routes

    def find_duplicate_ips(self, interface_output):
        """Find addresses assigned to more than one interface."""
        owners = defaultdict(list)
        for record in self.parse_interface_brief(interface_output):
            owners[record["ip"]].append(record["interface"])
        return {
            address: interfaces
            for address, interfaces in owners.items()
            if len(interfaces) > 1
        }

    def find_incorrect_subnet_masks(self, configuration):
        """Find masks that are non-contiguous or do not describe a host address."""
        errors = []
        for match in self._CONFIG_ADDRESS.finditer(self._text(configuration)):
            address = self._address(match.group("ip"))
            network = self._network(match.group("ip"), match.group("mask"))
            if address is None or network is None:
                errors.append(
                    {"ip": match.group("ip"), "mask": match.group("mask"), "reason": "invalid mask"}
                )
            elif address == network.network_address or address == network.broadcast_address:
                errors.append(
                    {
                        "ip": str(address),
                        "mask": match.group("mask"),
                        "reason": "interface address is a network or broadcast address",
                    }
                )
        return errors

    def find_default_gateway_mismatches(self, configuration):
        """Find a default gateway outside every configured interface subnet."""
        gateway = self.parse_default_gateway(configuration)
        if gateway is None:
            return []
        networks = [item["network"] for item in self.parse_interface_addresses(configuration)]
        if networks and not any(ipaddress.ip_address(gateway) in network for network in networks):
            return [{"gateway": gateway, "reason": "gateway is outside configured interface subnets"}]
        return []

    def find_administratively_down(self, interface_output):
        """Return interfaces whose status is explicitly administratively down."""
        return [
            record["interface"]
            for record in self.parse_interface_brief(interface_output)
            if record["status"] == "administratively down"
        ]

    def find_missing_routes(self, route_output, required_networks):
        """Return required destinations absent from the routing table."""
        routes = set(self.parse_routes(route_output))
        missing = []
        for destination in required_networks or ():
            try:
                network = ipaddress.ip_network(destination, strict=False)
            except ValueError:
                continue
            if network not in routes:
                missing.append(str(network))
        return missing

    def check(self, configurations, required_networks=()):
        """Run all checks and return a dictionary containing only identified errors.

        ``configurations`` may contain ``interface_brief``, ``interface_config``,
        and ``route_output`` strings. Missing or non-string inputs are treated as
        unavailable data and do not raise parsing exceptions.
        """
        if not isinstance(configurations, Mapping):
            return {"input": ["configurations must be a mapping"]}

        interface_output = configurations.get("interface_brief", "")
        interface_config = configurations.get("interface_config", "")
        route_output = configurations.get("route_output", "")
        errors = {}
        duplicate_ips = self.find_duplicate_ips(interface_output)
        incorrect_masks = self.find_incorrect_subnet_masks(interface_config)
        gateway_mismatches = self.find_default_gateway_mismatches(interface_config)
        admin_down = self.find_administratively_down(interface_output)
        missing_routes = self.find_missing_routes(route_output, required_networks)

        if duplicate_ips:
            errors["duplicate_ip_addresses"] = duplicate_ips
        if incorrect_masks:
            errors["incorrect_subnet_masks"] = incorrect_masks
        if gateway_mismatches:
            errors["default_gateway_mismatches"] = gateway_mismatches
        if admin_down:
            errors["administratively_down_interfaces"] = admin_down
        if missing_routes:
            errors["missing_routes"] = missing_routes
        return errors


if __name__ == "__main__":
    checker = NetworkRuleChecker()
    sample = {
        "interface_brief": (
            "Interface              IP-Address      OK? Method Status                Protocol\n"
            "GigabitEthernet0/1     10.44.8.9       YES manual administratively down down\n"
            "GigabitEthernet0/2     10.44.8.9       YES manual up                    up"
        ),
        "interface_config": (
            " ip address 10.44.8.9 255.255.255.0\n"
            " ip default-gateway 10.44.9.1\n"
        ),
        "route_output": "C    10.44.8.0/24 is directly connected, GigabitEthernet0/1",
    }
    print(checker.check(sample, required_networks=("172.31.90.0/24",)))
