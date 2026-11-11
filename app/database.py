"""
Database module for Internet Statistics and Speed Tester.
Manages SQLite storage for network profiles, speed test benchmarks, and telemetry logs.
"""
import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DB_DIR / "internet_tester.db"

def get_db_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Network profiles table: remembers each connection and its friendly name
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS networks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT UNIQUE NOT NULL,
            custom_name TEXT NOT NULL,
            detected_type TEXT,
            ssid TEXT,
            gateway_ip TEXT,
            public_ip TEXT,
            isp TEXT,
            city TEXT,
            country TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)

    # Speed test benchmark results
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS speed_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            network_id INTEGER,
            network_name TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            download_mbps REAL NOT NULL,
            upload_mbps REAL NOT NULL,
            ping_ms REAL NOT NULL,
            jitter_ms REAL DEFAULT 0.0,
            packet_loss_pct REAL DEFAULT 0.0,
            bufferbloat_grade TEXT,
            gaming_grade TEXT,
            streaming_grade TEXT,
            server_name TEXT,
            server_country TEXT,
            raw_data TEXT,
            FOREIGN KEY (network_id) REFERENCES networks(id) ON DELETE SET NULL
        )
    """)

    # Rolling ping / telemetry logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ping_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            network_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            target TEXT NOT NULL,
            latency_ms REAL,
            jitter_ms REAL,
            packet_loss_pct REAL,
            bytes_recv_rate REAL,
            bytes_sent_rate REAL,
            FOREIGN KEY (network_id) REFERENCES networks(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()

# Database Helper Functions
def get_or_create_network(
    fingerprint: str,
    default_name: str,
    detected_type: str = "ethernet",
    ssid: Optional[str] = None,
    gateway_ip: Optional[str] = None,
    public_ip: Optional[str] = None,
    isp: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = None
) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM networks WHERE fingerprint = ?", (fingerprint,))
    row = cursor.fetchone()

    now = datetime.now().isoformat()
    if row:
        # Update last_seen and public IP/ISP if available
        cursor.execute("""
            UPDATE networks 
            SET last_seen = ?,
                public_ip = COALESCE(?, public_ip),
                isp = COALESCE(?, isp),
                city = COALESCE(?, city),
                country = COALESCE(?, country),
                gateway_ip = COALESCE(?, gateway_ip),
                ssid = COALESCE(?, ssid)
            WHERE id = ?
        """, (now, public_ip, isp, city, country, gateway_ip, ssid, row["id"]))
        conn.commit()
        cursor.execute("SELECT * FROM networks WHERE id = ?", (row["id"],))
        result = dict(cursor.fetchone())
    else:
        cursor.execute("""
            INSERT INTO networks (
                fingerprint, custom_name, detected_type, ssid, gateway_ip, 
                public_ip, isp, city, country, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fingerprint, default_name, detected_type, ssid, gateway_ip,
            public_ip, isp, city, country, now, now
        ))
        conn.commit()
        network_id = cursor.lastrowid
        cursor.execute("SELECT * FROM networks WHERE id = ?", (network_id,))
        result = dict(cursor.fetchone())

    conn.close()
    return result

def rename_network(network_id: int, new_name: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE networks SET custom_name = ? WHERE id = ?", (new_name.strip(), network_id))
    rows_affected = cursor.rowcount
    # Also update network_name in speed_tests for consistency
    cursor.execute("UPDATE speed_tests SET network_name = ? WHERE network_id = ?", (new_name.strip(), network_id))
    conn.commit()
    conn.close()
    return rows_affected > 0

def get_all_networks() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.*, 
            COUNT(s.id) as test_count,
            AVG(s.download_mbps) as avg_download,
            AVG(s.upload_mbps) as avg_upload,
            AVG(s.ping_ms) as avg_ping
        FROM networks n
        LEFT JOIN speed_tests s ON n.id = s.network_id
        GROUP BY n.id
        ORDER BY n.last_seen DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def save_speed_test(test_data: Dict[str, Any]) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO speed_tests (
            network_id, network_name, timestamp, download_mbps, upload_mbps,
            ping_ms, jitter_ms, packet_loss_pct, bufferbloat_grade,
            gaming_grade, streaming_grade, server_name, server_country, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        test_data.get("network_id"),
        test_data.get("network_name", "Unknown Connection"),
        test_data.get("timestamp", datetime.now().isoformat()),
        test_data.get("download_mbps", 0.0),
        test_data.get("upload_mbps", 0.0),
        test_data.get("ping_ms", 0.0),
        test_data.get("jitter_ms", 0.0),
        test_data.get("packet_loss_pct", 0.0),
        test_data.get("bufferbloat_grade", "A"),
        test_data.get("gaming_grade", "A"),
        test_data.get("streaming_grade", "A"),
        test_data.get("server_name", ""),
        test_data.get("server_country", ""),
        json.dumps(test_data.get("raw_data", {}))
    ))
    conn.commit()
    test_id = cursor.lastrowid
    conn.close()
    return test_id

def get_speed_tests(network_id: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if network_id:
        cursor.execute("""
            SELECT * FROM speed_tests 
            WHERE network_id = ? 
            ORDER BY timestamp DESC LIMIT ?
        """, (network_id, limit))
    else:
        cursor.execute("""
            SELECT * FROM speed_tests 
            ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def delete_speed_test(test_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM speed_tests WHERE id = ?", (test_id,))
    conn.commit()
    rows = cursor.rowcount
    conn.close()
    return rows > 0

def clear_all_history(network_id: Optional[int] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if network_id:
        cursor.execute("DELETE FROM speed_tests WHERE network_id = ?", (network_id,))
        cursor.execute("DELETE FROM ping_logs WHERE network_id = ?", (network_id,))
    else:
        cursor.execute("DELETE FROM speed_tests")
        cursor.execute("DELETE FROM ping_logs")
    conn.commit()
    conn.close()

def save_ping_log(log: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ping_logs (
            network_id, timestamp, target, latency_ms, jitter_ms, 
            packet_loss_pct, bytes_recv_rate, bytes_sent_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        log.get("network_id"),
        log.get("timestamp", datetime.now().isoformat()),
        log.get("target", "1.1.1.1"),
        log.get("latency_ms"),
        log.get("jitter_ms"),
        log.get("packet_loss_pct"),
        log.get("bytes_recv_rate"),
        log.get("bytes_sent_rate")
    ))
    conn.commit()
    # Prune old logs keeping max 5,000 entries
    cursor.execute("DELETE FROM ping_logs WHERE id NOT IN (SELECT id FROM ping_logs ORDER BY id DESC LIMIT 5000)")
    conn.commit()
    conn.close()

def get_analytics_summary(network_id: Optional[int] = None) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()

    where_clause = "WHERE network_id = ?" if network_id else ""
    params = (network_id,) if network_id else ()

    cursor.execute(f"""
        SELECT 
            COUNT(*) as total_tests,
            COALESCE(MAX(download_mbps), 0) as max_download,
            COALESCE(AVG(download_mbps), 0) as avg_download,
            COALESCE(MIN(download_mbps), 0) as min_download,
            COALESCE(MAX(upload_mbps), 0) as max_upload,
            COALESCE(AVG(upload_mbps), 0) as avg_upload,
            COALESCE(MIN(upload_mbps), 0) as min_upload,
            COALESCE(MIN(ping_ms), 0) as min_ping,
            COALESCE(AVG(ping_ms), 0) as avg_ping,
            COALESCE(MAX(ping_ms), 0) as max_ping,
            COALESCE(AVG(jitter_ms), 0) as avg_jitter,
            COALESCE(AVG(packet_loss_pct), 0) as avg_packet_loss
        FROM speed_tests {where_clause}
    """, params)
    
    summary = dict(cursor.fetchone())
    conn.close()
    return summary
