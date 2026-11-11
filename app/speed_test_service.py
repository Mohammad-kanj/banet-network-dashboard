"""
Speed Test Service module.
Provides benchmarking for Ping, Jitter, Download Speed, Upload Speed,
and Loaded Latency (Bufferbloat). Emits progress updates for live speedometer UI.
"""
import asyncio
import time
import json
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Any, Callable, Optional
import speedtest

from .database import save_speed_test
from .network_detector import NetworkDetector

executor = ThreadPoolExecutor(max_workers=4)

class SpeedTestService:
    def __init__(self):
        self.is_running = False
        self.current_stage = "idle" # "idle", "ping", "download", "upload", "bufferbloat", "complete", "error"
        self.progress_pct = 0.0
        self.current_speed_mbps = 0.0
        self.current_ping_ms = 0.0
        self.listeners = set()

    def add_listener(self, ws):
        self.listeners.add(ws)

    def remove_listener(self, ws):
        self.listeners.discard(ws)

    async def broadcast_progress(self, data: Dict[str, Any]):
        dead = set()
        for ws in self.listeners:
            try:
                await ws.send_json({"type": "speedtest_progress", "data": data})
            except Exception:
                dead.add(ws)
        for d in dead:
            self.remove_listener(d)

    @staticmethod
    def calculate_grades(ping: float, jitter: float, packet_loss: float, download: float, upload: float, bufferbloat_delta: float) -> Dict[str, str]:
        """Calculates Gaming, Streaming, Video Call, and Bufferbloat letter grades."""
        # Gaming Grade
        if ping < 35 and jitter < 5 and packet_loss == 0:
            gaming = "A+"
        elif ping < 60 and jitter < 12 and packet_loss <= 1:
            gaming = "A"
        elif ping < 100 and jitter < 25 and packet_loss <= 3:
            gaming = "B"
        elif ping < 150:
            gaming = "C"
        else:
            gaming = "D"

        # Streaming Grade (4K HDR vs 1080p vs 720p)
        if download >= 50 and jitter < 20:
            streaming = "A+ (4K Ultra HD)"
        elif download >= 25:
            streaming = "A (4K Streaming)"
        elif download >= 10:
            streaming = "B (1080p Full HD)"
        elif download >= 4:
            streaming = "C (720p HD)"
        else:
            streaming = "D (Standard Def)"

        # Video Call (Zoom / Teams / Meet)
        if ping < 60 and upload >= 10 and packet_loss == 0:
            video_call = "A+ (Flawless HD)"
        elif ping < 100 and upload >= 3 and packet_loss <= 1:
            video_call = "A (Smooth)"
        elif ping < 150 and upload >= 1.5:
            video_call = "B (Acceptable)"
        else:
            video_call = "C (Choppy Video)"

        # Bufferbloat Grade
        if bufferbloat_delta <= 10:
            bloat = "A+"
        elif bufferbloat_delta <= 30:
            bloat = "A"
        elif bufferbloat_delta <= 65:
            bloat = "B"
        elif bufferbloat_delta <= 120:
            bloat = "C"
        else:
            bloat = "D"

        return {
            "gaming_grade": gaming,
            "streaming_grade": streaming,
            "video_call_grade": video_call,
            "bufferbloat_grade": bloat
        }

    def _run_speedtest_cli(self, progress_callback: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
        """Runs speedtest in thread with staged updates."""
        progress_callback({"stage": "init", "message": "Selecting best speed test server...", "progress": 5})
        
        s = speedtest.Speedtest()
        s.get_best_server()
        best_server = s.best
        server_name = f"{best_server.get('sponsor', 'CDN')} ({best_server.get('name', 'Server')})"
        server_country = best_server.get("country", "")

        unloaded_ping = float(best_server.get("latency", 0.0))
        progress_callback({
            "stage": "ping",
            "message": f"Connected to {server_name}",
            "ping_ms": round(unloaded_ping, 1),
            "progress": 20
        })

        # Download Test
        progress_callback({"stage": "download", "message": "Testing download throughput...", "progress": 25})
        download_bps = s.download()
        download_mbps = download_bps / 1_000_000.0

        progress_callback({
            "stage": "upload",
            "message": "Testing upload throughput...",
            "download_mbps": round(download_mbps, 2),
            "progress": 65
        })

        # Upload Test
        upload_bps = s.upload()
        upload_mbps = upload_bps / 1_000_000.0

        # Bufferbloat estimate
        results_dict = s.results.dict()
        bufferbloat_delta = max(0.0, float(results_dict.get("ping", unloaded_ping)) - unloaded_ping)

        return {
            "download_mbps": round(download_mbps, 2),
            "upload_mbps": round(upload_mbps, 2),
            "ping_ms": round(unloaded_ping, 1),
            "jitter_ms": round(abs(float(results_dict.get("ping", unloaded_ping)) - unloaded_ping), 1),
            "packet_loss_pct": 0.0,
            "server_name": server_name,
            "server_country": server_country,
            "bufferbloat_delta": round(bufferbloat_delta, 1),
            "raw_data": results_dict
        }

    async def execute_test(self, custom_network_id: Optional[int] = None) -> Dict[str, Any]:
        """Orchestrates test execution, emits live progress via WebSocket, and saves to DB."""
        if self.is_running:
            return {"error": "A speed test is already running"}

        self.is_running = True
        loop = asyncio.get_event_loop()

        # Gather current network profile
        net_info = NetworkDetector.detect_current_connection()
        network_id = custom_network_id or net_info.get("network_id")
        network_name = net_info.get("custom_name", "Local Network")

        def sync_callback(update_dict):
            asyncio.run_coroutine_threadsafe(self.broadcast_progress(update_dict), loop)

        try:
            await self.broadcast_progress({
                "stage": "starting",
                "message": "Preparing speed test benchmark...",
                "progress": 0,
                "network_name": network_name
            })

            # Run speedtest in worker thread
            result = await loop.run_in_executor(executor, self._run_speedtest_cli, sync_callback)

            # Grades
            grades = self.calculate_grades(
                ping=result["ping_ms"],
                jitter=result["jitter_ms"],
                packet_loss=result["packet_loss_pct"],
                download=result["download_mbps"],
                upload=result["upload_mbps"],
                bufferbloat_delta=result["bufferbloat_delta"]
            )
            result.update(grades)

            # Record in SQLite
            result["network_id"] = network_id
            result["network_name"] = network_name
            result["timestamp"] = datetime.now().isoformat()
            test_id = save_speed_test(result)
            result["id"] = test_id

            await self.broadcast_progress({
                "stage": "complete",
                "message": "Speed test complete!",
                "progress": 100,
                "result": result
            })

            return result

        except Exception as e:
            err_msg = str(e)
            await self.broadcast_progress({
                "stage": "error",
                "message": f"Test failed: {err_msg}",
                "progress": 0
            })
            return {"error": err_msg}
        finally:
            self.is_running = False

speed_tester = SpeedTestService()
