"""
Launcher for Banet - Live Internet Statistics & Speed Tester.
Starts local server and opens browser automatically.
"""
import sys
import socket
import webbrowser
import threading
import time
import uvicorn

def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0

def find_available_port(start_port: int = 8000, max_attempts: int = 10) -> int:
    for port in range(start_port, start_port + max_attempts):
        if is_port_free(port):
            return port
    return start_port

def open_browser_after_delay(url: str, delay: float = 1.0):
    time.sleep(delay)
    print(f"[*] Opening browser: {url}")
    webbrowser.open(url)

def main():
    port = find_available_port(8000)
    url = f"http://127.0.0.1:{port}"

    print("=" * 60)
    print("      BANET - LIVE INTERNET STATISTICS & SPEED TESTER")
    print("=" * 60)
    print(f"[*] Server starting on: {url}")
    print("[*] Tracking live ping, jitter, packet loss, bandwidth & speeds")
    print("[*] No login required • Networks remembered automatically")
    print("=" * 60)

    # Launch browser in a background thread
    threading.Thread(target=open_browser_after_delay, args=(url,), daemon=True).start()

    # Run Uvicorn server
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="info")

if __name__ == "__main__":
    main()
