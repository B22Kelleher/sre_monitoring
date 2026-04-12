import requests
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

PROMETHEUS_URL = "http://localhost:9090"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
print(f"USER={SMTP_USER}, PASS={SMTP_PASS}")
EMAIL_TO = os.environ.get("REPORT_EMAIL", SMTP_USER)


def query_prometheus(promql):
    """Query the Prometheus HTTP API and return the first result value."""
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": promql},
            timeout=5
        )
        response.raise_for_status()
        results = response.json().get("data", {}).get("result", [])
        if results:
            return float(results[0]["value"][1])
        return None
    except Exception as e:
        print(f"Query failed for '{promql}': {e}")
        return None


def get_metrics():
    """Collect key system health metrics from Prometheus."""
    metrics = {}

    # CPU usage % (average across all cores, last 5 minutes)
    cpu = query_prometheus(
        '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
    )
    metrics["CPU Usage"] = f"{cpu:.1f}%" if cpu is not None else "N/A"

    # Memory usage %
    mem = query_prometheus(
        "(1 - ((node_memory_MemFree_bytes + node_memory_Buffers_bytes + node_memory_Cached_bytes) / node_memory_MemTotal_bytes)) * 100"
    )
    metrics["Memory Usage"] = f"{mem:.1f}%" if mem is not None else "N/A"

    # Disk usage % for root filesystem
    disk = query_prometheus(
        '100 * (1 - (node_filesystem_avail_bytes{mountpoint="/run"} / node_filesystem_size_bytes{mountpoint="/run"}))'
    )
    metrics["Disk Usage"] = f"{disk:.1f}%" if disk is not None else "N/A"

    # System uptime in hours
    uptime = query_prometheus("(time() - node_boot_time_seconds) / 3600")
    metrics["Uptime"] = f"{uptime:.1f} hours" if uptime is not None else "N/A"

    # Network receive rate (KB/s, last 5 minutes)
    net_rx = query_prometheus(
        'sum(rate(node_network_receive_bytes_total[5m])) / 1024'
    )
    metrics["Network RX"] = f"{net_rx:.1f} KB/s" if net_rx is not None else "N/A"

    # Network transmit rate (KB/s, last 5 minutes)
    net_tx = query_prometheus(
        'sum(rate(node_network_transmit_bytes_total[5m])) / 1024'
    )
    metrics["Network TX"] = f"{net_tx:.1f} KB/s" if net_tx is not None else "N/A"

    return metrics


def flag_alerts(metrics):
    """Return simple threshold-based warnings."""
    alerts = []
    thresholds = {
        "CPU Usage": 85,
        "Memory Usage": 90,
        "Disk Usage": 80,
    }
    for key, threshold in thresholds.items():
        value = metrics.get(key, "N/A")
        if value != "N/A":
            numeric = float(value.replace("%", ""))
            if numeric >= threshold:
                alerts.append(f"WARNING: {key} is at {value} (threshold: {threshold}%)")
    return alerts


def build_email(metrics, alerts):
    """Build a plain-text email body from metrics and alerts."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"System Health Report — {now}",
        "=" * 40,
        "",
    ]

    if alerts:
        lines.append("ALERTS:")
        for alert in alerts:
            lines.append(f"  {alert}")
        lines.append("")

    lines.append("METRICS:")
    for key, value in metrics.items():
        lines.append(f"  {key:<20} {value}")

    lines += [
        "",
        "=" * 40,
        "View full dashboard: https://wobbling-bunkhouse-gilled.ngrok-free.dev/?orgId=1&from=now-6h&to=now&timezone=browser"
        "Generated automatically by prometheus_report.py",
    ]
    return "\n".join(lines)


def send_email(subject, body):
    """Send the report email via Gmail SMTP."""
    if not SMTP_USER or not SMTP_PASS:
        print("Email credentials not set. Set SMTP_USER and SMTP_PASS env vars.")
        print("\n--- REPORT PREVIEW ---")
        print(body)
        return

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
    print(f"Report sent to {EMAIL_TO}")


if __name__ == "__main__":
    print("Querying Prometheus...")
    metrics = get_metrics()
    alerts = flag_alerts(metrics)
    subject = f"[{'ALERT' if alerts else 'OK'}] System Health Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    body = build_email(metrics, alerts)
    send_email(subject, body)