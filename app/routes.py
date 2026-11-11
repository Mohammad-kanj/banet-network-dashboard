"""
API Routes and WebSocket handling for the Internet Statistics & Speed Tester.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import io
import csv
import json

from .database import (
    rename_network, get_all_networks, get_speed_tests,
    delete_speed_test, clear_all_history, get_analytics_summary
)
from .network_detector import NetworkDetector
from .network_optimizer import NetworkOptimizer
from .live_monitor import monitor
from .speed_test_service import speed_tester

router = APIRouter()

class RenameRequest(BaseModel):
    network_id: int
    custom_name: str

class TargetRequest(BaseModel):
    target: str

class GatewayRequest(BaseModel):
    gateway_ip: Optional[str] = "192.168.1.1"

@router.post("/api/network/optimize")
def optimize_network(req: GatewayRequest = GatewayRequest()):
    """Flushes local DNS cache, resets network routing buffers, and benchmarks improvement."""
    gw = req.gateway_ip or (monitor._current_network.get("gateway_ip") if monitor._current_network else "192.168.1.1")
    return NetworkOptimizer.optimize_connection(gateway_ip=gw)

@router.post("/api/network/reboot-router")
def reboot_router(req: GatewayRequest = GatewayRequest()):
    """Attempts router reboot via UPnP and prepares direct gateway console access."""
    gw = req.gateway_ip or (monitor._current_network.get("gateway_ip") if monitor._current_network else "192.168.1.1")
    return NetworkOptimizer.attempt_router_reboot(gateway_ip=gw)

@router.get("/api/network/current")
def get_current_network():
    """Returns detected network details and saved friendly name."""
    return NetworkDetector.detect_current_connection(force_refresh=True)

@router.post("/api/network/rename")
def update_network_name(req: RenameRequest):
    """Saves user-defined custom name for this network so it is remembered permanently."""
    success = rename_network(req.network_id, req.custom_name)
    if not success:
        raise HTTPException(status_code=404, detail="Network profile not found")
    # Refresh in monitor
    monitor._current_network = NetworkDetector.detect_current_connection(force_refresh=True)
    return {"status": "ok", "custom_name": req.custom_name.strip()}

@router.get("/api/network/list")
def list_networks():
    """Lists all remembered network profiles."""
    return get_all_networks()

@router.post("/api/speedtest/start")
async def start_speedtest(network_id: Optional[int] = Query(None)):
    """Triggers a benchmark speed test."""
    if speed_tester.is_running:
        raise HTTPException(status_code=409, detail="Speed test already in progress")
    # Launch asynchronously
    import asyncio
    asyncio.create_task(speed_tester.execute_test(custom_network_id=network_id))
    return {"status": "started", "message": "Speed test started in background"}

@router.get("/api/speedtest/status")
def speedtest_status():
    return {
        "is_running": speed_tester.is_running,
        "stage": speed_tester.current_stage
    }

@router.get("/api/speedtest/history")
def history(network_id: Optional[int] = Query(None), limit: int = Query(100)):
    return get_speed_tests(network_id=network_id, limit=limit)

@router.delete("/api/speedtest/{test_id}")
def delete_test(test_id: int):
    success = delete_speed_test(test_id)
    if not success:
        raise HTTPException(status_code=404, detail="Test record not found")
    return {"status": "deleted", "id": test_id}

@router.post("/api/speedtest/clear")
def clear_history(network_id: Optional[int] = Query(None)):
    clear_all_history(network_id=network_id)
    return {"status": "cleared"}

@router.get("/api/analytics/summary")
def analytics_summary(network_id: Optional[int] = Query(None)):
    return get_analytics_summary(network_id=network_id)

@router.get("/api/monitor/live")
def get_live_telemetry():
    """Returns current live ping, jitter, packet loss and bandwidth telemetry."""
    return monitor.latest_stats

@router.post("/api/monitor/target")
def change_ping_target(req: TargetRequest):
    monitor.set_target(req.target)
    return {"status": "ok", "target": monitor.primary_target}

@router.get("/api/export/csv")
def export_csv(network_id: Optional[int] = Query(None)):
    tests = get_speed_tests(network_id=network_id, limit=1000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Timestamp", "Network Name", "Download (Mbps)", "Upload (Mbps)",
        "Ping (ms)", "Jitter (ms)", "Packet Loss (%)", "Bufferbloat Grade",
        "Gaming Grade", "Streaming Grade", "Server"
    ])
    for t in tests:
        writer.writerow([
            t.get("id"),
            t.get("timestamp"),
            t.get("network_name"),
            t.get("download_mbps"),
            t.get("upload_mbps"),
            t.get("ping_ms"),
            t.get("jitter_ms"),
            t.get("packet_loss_pct"),
            t.get("bufferbloat_grade"),
            t.get("gaming_grade"),
            t.get("streaming_grade"),
            t.get("server_name")
        ])
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=internet_speed_history.csv"}
    )

@router.get("/api/export/json")
def export_json(network_id: Optional[int] = Query(None)):
    tests = get_speed_tests(network_id=network_id, limit=1000)
    summary = get_analytics_summary(network_id=network_id)
    return {
        "summary": summary,
        "tests": tests
    }

@router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    monitor.register_client(websocket)
    speed_tester.add_listener(websocket)
    # Send immediate initial stats
    await websocket.send_json(monitor.latest_stats)
    try:
        while True:
            # Keep socket alive and allow client to send commands
            data = await websocket.receive_text()
            try:
                cmd = json.loads(data)
                if cmd.get("action") == "set_target":
                    monitor.set_target(cmd.get("target", "1.1.1.1"))
                elif cmd.get("action") == "start_test":
                    if not speed_tester.is_running:
                        import asyncio
                        asyncio.create_task(speed_tester.execute_test())
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        monitor.unregister_client(websocket)
        speed_tester.remove_listener(websocket)
