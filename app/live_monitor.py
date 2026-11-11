"""
Live Monitor module for Banet.
Runs continuous real-time pinging, packet loss calculation, jitter measurement,
and interface I/O bandwidth tracking. Supports ICMP ping with transparent TCP ping fallback.
Broadcasts updates via WebSockets and REST endpoint.
"""
import asyncio
import re
import time
import socket
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Dict, Any, Optional
import psutil

from .database import save_ping_log
from .network_detector import NetworkDetector

thread_pool = ThreadPoolExecutor(max_workers=4)

# Regex matching multilingual ping outputs (English, French, German, Spanish, etc.)
PING_REGEX = re.compile(
    r'(?:time|zeit|temps|tiempo|tempo|durata)[=<](\d+(?:\.\d+)?)\s*ms|[=<](\d+)\s*ms',
    re.IGNORECASE
)

class LiveMonitor:
    def __init__(self):
        self.running = False
        self.primary_target = "1.1.1.1" # Fast Global Edge
        self.secondary_targets = ["8.8.8.8"]
        self.gateway_target = "192.168.1.1"

        # Rolling window for metrics (last 30 seconds / pings)
        self.ping_history = deque(maxlen=30)
        self.loss_history = deque(maxlen=30)
        
        # Traffic I/O tracking
        self.last_io = None
        self.last_io_time = None
        self.current_download_rate = 0.0 # bytes/sec
        self.current_upload_rate = 0.0 # bytes/sec

        # Cached latest snapshot
        self.latest_stats: Dict[str, Any] = {
            "status": "online",
            "primary_target": self.primary_target,
            "target_label": "Global Fast Edge",
            "ping_ms": None,
            "min_ping": None,
            "max_ping": None,
            "avg_ping": None,
            "jitter_ms": 0.0,
            "packet_loss_pct": 0.0,
            "download_bps": 0.0,
            "upload_bps": 0.0,
            "download_mbps": 0.0,
            "upload_mbps": 0.0,
            "total_bytes_recv": 0,
            "total_bytes_sent": 0,
            "targets": {},
            "timestamp": datetime.now().isoformat()
        }

        # WebSocket subscribers
        self.subscribers = set()
        self._task = None
        self._current_network = None
        self._log_counter = 0

    def register_client(self, websocket):
        self.subscribers.add(websocket)

    def unregister_client(self, websocket):
        self.subscribers.discard(websocket)

    def set_target(self, new_target: str):
        if new_target and new_target.strip():
            self.primary_target = new_target.strip()
            self.ping_history.clear()
            self.loss_history.clear()
            self.latest_stats["primary_target"] = self.primary_target

    @staticmethod
    def _tcp_ping_fallback(host: str, timeout: float = 1.2) -> Optional[float]:
        """Fast TCP connect ping fallback when ICMP is blocked or filtered."""
        candidate_ports = [443, 80, 53] if host not in ["1.1.1.1", "8.8.8.8"] else [53, 443]
        for port in candidate_ports:
            t0 = time.time()
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((host, port))
                s.close()
                elapsed = (time.time() - t0) * 1000.0
                return round(elapsed, 1)
            except Exception:
                continue
        return None

    async def _ping_host(self, host: str, timeout_ms: int = 1400) -> Optional[float]:
        """
        Runs ping with multilingual support and automatic TCP fallback if ICMP is dropped.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping.exe", "-n", "1", "-w", str(timeout_ms), host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=(timeout_ms / 1000.0 + 0.6))
                out = stdout.decode("cp1252", errors="ignore")
                match = PING_REGEX.search(out)
                if match:
                    val = match.group(1) or match.group(2)
                    return float(val) if val else 1.0
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
        except Exception:
            pass

        # Fallback to TCP handshake if ICMP ping failed or was blocked by firewall
        loop = asyncio.get_event_loop()
        try:
            tcp_result = await loop.run_in_executor(thread_pool, self._tcp_ping_fallback, host, timeout_ms / 1000.0)
            return tcp_result
        except Exception:
            return None

    def _update_bandwidth(self):
        """Measures delta I/O to compute current live download and upload rates."""
        now = time.time()
        try:
            current_io = psutil.net_io_counters()
            if self.last_io and self.last_io_time:
                dt = now - self.last_io_time
                if dt > 0:
                    delta_recv = current_io.bytes_recv - self.last_io.bytes_recv
                    delta_sent = current_io.bytes_sent - self.last_io.bytes_sent
                    
                    if delta_recv >= 0 and delta_sent >= 0:
                        self.current_download_rate = delta_recv / dt
                        self.current_upload_rate = delta_sent / dt
            
            self.last_io = current_io
            self.last_io_time = now
        except Exception:
            pass

    async def run_loop(self):
        """Main 1-second monitoring loop."""
        self.running = True
        self.last_io = psutil.net_io_counters()
        self.last_io_time = time.time()
        loop = asyncio.get_event_loop()

        # Run initial network detect in background executor so loop isn't delayed
        try:
            self._current_network = await loop.run_in_executor(thread_pool, NetworkDetector.detect_current_connection)
            if self._current_network and self._current_network.get("gateway_ip"):
                self.gateway_target = self._current_network["gateway_ip"]
        except Exception:
            pass

        secondary_cycle = 0

        while self.running:
            t0 = time.time()
            self._update_bandwidth()

            # Ping primary target
            latency = await self._ping_host(self.primary_target)

            if latency is not None:
                self.ping_history.append(latency)
                self.loss_history.append(0)
            else:
                self.loss_history.append(1)

            # Compute metrics over rolling history
            valid_pings = list(self.ping_history)
            recent_losses = list(self.loss_history)

            loss_pct = (sum(recent_losses) / len(recent_losses) * 100.0) if recent_losses else 0.0
            
            if valid_pings:
                curr_ping = valid_pings[-1]
                min_p = min(valid_pings)
                max_p = max(valid_pings)
                avg_p = sum(valid_pings) / len(valid_pings)

                # RFC 3550 Interarrival Jitter calculation
                if len(valid_pings) > 1:
                    diffs = [abs(valid_pings[i] - valid_pings[i-1]) for i in range(1, len(valid_pings))]
                    jitter = sum(diffs) / len(diffs)
                else:
                    jitter = 0.0
            else:
                curr_ping = None
                min_p = None
                max_p = None
                avg_p = None
                jitter = 0.0

            # Periodic secondary ping for comparison (every 5 seconds)
            secondary_cycle += 1
            targets_stat = self.latest_stats.get("targets", {})
            targets_stat[self.primary_target] = curr_ping

            if secondary_cycle % 5 == 0:
                async def ping_bg(target_host):
                    res = await self._ping_host(target_host, timeout_ms=800)
                    targets_stat[target_host] = res

                await asyncio.gather(
                    ping_bg("8.8.8.8"),
                    ping_bg(self.gateway_target),
                    return_exceptions=True
                )

            # Determine connection status
            if loss_pct >= 90:
                status = "offline"
            elif loss_pct > 10 or (curr_ping and curr_ping > 250):
                status = "degraded"
            else:
                status = "online"

            # Build telemetry packet
            snapshot = {
                "status": status,
                "primary_target": self.primary_target,
                "ping_ms": round(curr_ping, 1) if curr_ping is not None else None,
                "min_ping": round(min_p, 1) if min_p is not None else None,
                "max_ping": round(max_p, 1) if max_p is not None else None,
                "avg_ping": round(avg_p, 1) if avg_p is not None else None,
                "jitter_ms": round(jitter, 1),
                "packet_loss_pct": round(loss_pct, 1),
                "download_bps": round(self.current_download_rate, 1),
                "upload_bps": round(self.current_upload_rate, 1),
                "download_mbps": round((self.current_download_rate * 8) / 1_000_000, 2),
                "upload_mbps": round((self.current_upload_rate * 8) / 1_000_000, 2),
                "total_bytes_recv": self.last_io.bytes_recv if self.last_io else 0,
                "total_bytes_sent": self.last_io.bytes_sent if self.last_io else 0,
                "targets": targets_stat,
                "timestamp": datetime.now().isoformat()
            }
            self.latest_stats = snapshot

            # Periodically (every 15s) persist to SQLite
            self._log_counter += 1
            if self._log_counter >= 15:
                self._log_counter = 0
                try:
                    network_id = self._current_network.get("network_id") if self._current_network else None
                    save_ping_log({
                        "network_id": network_id,
                        "timestamp": snapshot["timestamp"],
                        "target": self.primary_target,
                        "latency_ms": snapshot["ping_ms"],
                        "jitter_ms": snapshot["jitter_ms"],
                        "packet_loss_pct": snapshot["packet_loss_pct"],
                        "bytes_recv_rate": snapshot["download_bps"],
                        "bytes_sent_rate": snapshot["upload_bps"]
                    })
                except Exception:
                    pass

            # Broadcast to active WebSockets
            if self.subscribers:
                dead_sockets = set()
                for ws in self.subscribers:
                    try:
                        await ws.send_json(snapshot)
                    except Exception:
                        dead_sockets.add(ws)
                for ds in dead_sockets:
                    self.unregister_client(ds)

            # Sleep remainder of 1 second
            elapsed = time.time() - t0
            sleep_duration = max(0.05, 1.0 - elapsed)
            await asyncio.sleep(sleep_duration)

    def start(self):
        if not self.running:
            self._task = asyncio.create_task(self.run_loop())

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()

# Global singleton monitor
monitor = LiveMonitor()
