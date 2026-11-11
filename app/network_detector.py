"""
Network Detector module.
Detects active network adapters, Wi-Fi SSID, default gateway, public IP, ISP info,
and resolves or creates the persistent network profile in SQLite.
"""
import subprocess
import socket
import re
import json
import urllib.request
import psutil
from typing import Dict, Any, Optional
from .database import get_or_create_network

class NetworkDetector:
    _cached_info = None
    _last_check = 0

    @classmethod
    def get_local_ip(cls) -> str:
        """Finds primary local outbound IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @classmethod
    def get_wifi_details(cls) -> Optional[Dict[str, str]]:
        """Parses Windows netsh wlan output if connected to Wi-Fi."""
        try:
            cmd = ["netsh", "wlan", "show", "interfaces"]
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=2)
            
            if "State" in output and "connected" in output.lower():
                details = {}
                for line in output.splitlines():
                    if ":" in line:
                        parts = line.split(":", 1)
                        key = parts[0].strip()
                        val = parts[1].strip()
                        if key.lower() == "ssid":
                            details["ssid"] = val
                        elif key.lower() == "bssid":
                            details["bssid"] = val
                        elif key.lower() == "signal":
                            details["signal"] = val
                        elif key.lower() == "radio type":
                            details["radio_type"] = val
                        elif key.lower() == "channel":
                            details["channel"] = val
                if "ssid" in details and details["ssid"]:
                    return details
        except Exception:
            pass
        return None

    @classmethod
    def get_gateway_and_adapter(cls) -> Dict[str, str]:
        """Queries Windows default route for NextHop and InterfaceAlias."""
        result = {"gateway": "Unknown", "adapter": "Unknown"}
        try:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                "Get-NetRoute -DestinationPrefix 0.0.0.0/0 | Select-Object -First 1 NextHop, InterfaceAlias | ConvertTo-Json"
            ]
            raw = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=3)
            data = json.loads(raw)
            if isinstance(data, dict):
                result["gateway"] = data.get("NextHop", "Unknown")
                result["adapter"] = data.get("InterfaceAlias", "Unknown")
        except Exception:
            # Fallback
            result["gateway"] = "192.168.1.1"
            result["adapter"] = "Ethernet"
        return result

    @classmethod
    def get_public_ip_and_isp(cls) -> Dict[str, Any]:
        """Fetches public IP, ISP name, city, and country with graceful offline handling."""
        info = {
            "public_ip": "Unavailable",
            "isp": "Local Network",
            "city": "Unknown",
            "country": "Unknown",
            "org": "",
            "asn": ""
        }
        try:
            req = urllib.request.Request(
                "http://ip-api.com/json?fields=status,message,country,countryCode,regionName,city,isp,org,as,query",
                headers={"User-Agent": "curl/7.88.1"}
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "success":
                    info["public_ip"] = data.get("query", "Unavailable")
                    info["isp"] = data.get("isp", "Unknown ISP")
                    info["city"] = data.get("city", "Unknown")
                    info["country"] = data.get("country", "Unknown")
                    info["org"] = data.get("org", "")
                    info["asn"] = data.get("as", "")
                    return info
        except Exception:
            pass

        # Fallback to Cloudflare trace for public IP and country code
        try:
            req = urllib.request.Request("https://1.1.1.1/cdn-cgi/trace", headers={"User-Agent": "curl/7.88.1"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                raw = resp.read().decode("utf-8")
                for line in raw.splitlines():
                    if line.startswith("ip="):
                        info["public_ip"] = line.split("=", 1)[1]
                    elif line.startswith("loc="):
                        info["country"] = line.split("=", 1)[1]
                    elif line.startswith("colo="):
                        info["city"] = f"Cloudflare {line.split('=', 1)[1]}"
                info["isp"] = "Cloudflare Edge"
        except Exception:
            pass

        return info

    @classmethod
    def detect_current_connection(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Gathers full connection identity, determines connection fingerprint,
        and synchronizes with SQLite network profiles so named networks persist.
        """
        local_ip = cls.get_local_ip()
        wifi_info = cls.get_wifi_details()
        route_info = cls.get_gateway_and_adapter()
        public_info = cls.get_public_ip_and_isp()

        adapter_name = route_info.get("adapter", "Ethernet")
        gateway_ip = route_info.get("gateway", "192.168.1.1")
        public_ip = public_info.get("public_ip")
        isp = public_info.get("isp")
        city = public_info.get("city")
        country = public_info.get("country")

        if wifi_info and wifi_info.get("ssid"):
            detected_type = "wifi"
            ssid = wifi_info["ssid"]
            fingerprint = f"wifi:{ssid.lower()}"
            default_name = f"Wi-Fi ({ssid})"
        else:
            ssid = None
            if "vpn" in adapter_name.lower():
                detected_type = "vpn"
                fingerprint = f"vpn:{adapter_name}:{gateway_ip}:{isp}"
                default_name = f"VPN ({isp or adapter_name})"
            else:
                detected_type = "ethernet"
                fingerprint = f"eth:{adapter_name}:{gateway_ip}:{isp}"
                default_name = f"Ethernet ({isp or 'Network'})"

        # Check / retrieve persistent profile in SQLite
        profile = get_or_create_network(
            fingerprint=fingerprint,
            default_name=default_name,
            detected_type=detected_type,
            ssid=ssid,
            gateway_ip=gateway_ip,
            public_ip=public_ip,
            isp=isp,
            city=city,
            country=country
        )

        # Merge live dynamic connection details
        result = {
            "network_id": profile["id"],
            "custom_name": profile["custom_name"],
            "fingerprint": fingerprint,
            "detected_type": detected_type,
            "ssid": ssid,
            "wifi_details": wifi_info,
            "local_ip": local_ip,
            "gateway_ip": gateway_ip,
            "adapter_name": adapter_name,
            "public_ip": public_ip,
            "isp": isp,
            "city": city,
            "country": country,
            "org": public_info.get("org", ""),
            "asn": public_info.get("asn", ""),
            "first_seen": profile.get("first_seen"),
            "last_seen": profile.get("last_seen")
        }
        return result
