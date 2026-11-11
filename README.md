# Banet - Live Internet Statistics & Speed Tester

**Banet** is a smooth, real-time internet performance monitor, speed benchmark, and network optimization suite designed to run locally on your machine with **zero login required**. 

It continuously tracks live internet statistics, evaluates connection quality, auto-identifies your active network, **remembers connection names** for persistent historical analytics, and provides **tools to boost your connection and restart your router**.

---

## ⚡ Key Features

1. **Continuous Live HUD & Telemetry**:
   - **Real-Time Ping & Latency (ms)**: 1-second pulse monitoring with min/avg/max statistics.
   - **RFC 3550 Interarrival Jitter (ms)**: Real-time latency variance tracking for stability assessment.
   - **Rolling Packet Loss (%)**: Calculates packet drop percentage over a rolling 30-second window.
   - **Real-Time Adapter I/O Bandwidth**: Measures exact live download and upload bytes passing through your active network interface.
   - **One-Click Destination Switching**: Click any destination pill to switch live tracking instantly (**Global Fast Edge**, **Global Alternate**, **Quad9 Secure**, or **Home Router**).
   - **Live Waveform Charts**: Smooth real-time streaming line graphs powered by Chart.js.

2. **⚡ Improve Internet & Router Controls**:
   - **Quick Network Optimization**: Flushes Windows DNS resolver cache, purges stale routing paths, and verifies latency reduction.
   - **Restart Home Router**: Sends UPnP reboot/reconnect commands directly to your router gateway (`192.168.1.1`) to clear congested NAT state and re-establish a fresh ISP session.
   - **Direct Router Console Access**: One-click link to open your router's admin portal in your browser.

3. **On-Demand Speed Test Benchmark**:
   - **Speedometer**: Circular SVG speedometer with gradient neon animations.
   - **Multi-Phase Benchmark**: Ping test, server selection, download test, upload test, and bufferbloat estimation.
   - **Experience Grades**: Automatically calculates letter grades (A+ to D) for:
     - 🎮 **Gaming Score**: Evaluates low latency and low jitter for competitive esports.
     - 📺 **Streaming Score**: Verifies 4K Ultra HD and 1080p readiness.
     - 📹 **Video Conferencing**: Tests stability for Zoom, Microsoft Teams, and Google Meet.
     - 📶 **Bufferbloat Grade**: Measures latency increase while connection is fully loaded.

4. **Auto-Network Identification & Memory**:
   - Automatically detects whether you are on Wi-Fi (SSID, Signal), Ethernet, or a VPN tunnel.
   - Gathers public IP, ISP provider, Autonomous System (ASN), and Geolocation.
   - **Remembers Connection Names**: Click the edit button to label your network (e.g., *"Home 1G Fiber"*, *"Office Wi-Fi"*, *"ProtonVPN NYC"*). Banet stores this fingerprint in SQLite and automatically recognizes the network whenever you reconnect!

5. **Analytics & Historical Intelligence**:
   - Filter benchmarks by current connection or compare across all saved networks.
   - Track peak download, peak upload, average speeds, and lowest ping over time.
   - Benchmark history table with individual record deletion.
   - **One-Click Exports**: Export complete history to **CSV** (for Excel/Sheets) or **JSON**.

6. **Smooth Obsidian Glassmorphism UI**:
   - Clean, focused dark-mode theme with ambient neon glows and glassmorphism panels.
   - Fully local and offline-ready with bundled vendor scripts.

---

## 🚀 How to Run Locally

### Option A: One-Click Launcher (Windows)
Double-click `start.bat` in the project root:
```batch
start.bat
```
This automatically launches the server and opens your web browser to `http://localhost:8000`.

### Option B: Terminal Command
Run with Python:
```bash
python run.py
```

---

## 📁 Project Architecture

```
Internet Tester/
├── app/
│   ├── database.py             # SQLite storage for network profiles, tests, and ping logs
│   ├── network_detector.py     # Hardware adapter, SSID, gateway, and ISP detection
│   ├── network_optimizer.py    # DNS flush, routing refresh, and UPnP router restart
│   ├── live_monitor.py         # 1-second continuous ping, jitter, packet loss & I/O loop
│   ├── speed_test_service.py   # Benchmark engine with multi-phase reporting & grading
│   ├── routes.py               # REST API endpoints & real-time WebSocket stream
│   └── main.py                 # FastAPI application setup & lifecycle
├── static/
│   ├── css/
│   │   └── style.css           # Pure obsidian glassmorphism design system
│   ├── js/
│   │   └── app.js              # One-click targets, optimizer modal, WebSockets & Chart.js
│   ├── vendor/                 # Offline-ready Chart.js & Lucide icon scripts
│   └── index.html              # Single-page dashboard application
├── data/
│   └── internet_tester.db      # Embedded local SQLite database
├── run.py                      # Server starter with auto-port discovery & browser launcher
├── start.bat                   # 1-click Windows batch launcher
├── requirements.txt            # Python dependencies
└── README.md                   # Documentation
```

---

## 🔒 Privacy & Zero Login
- **No accounts or authentication required**.
- All ping logs, connection fingerprints, and speed test records are stored locally inside `data/internet_tester.db` on your machine.
