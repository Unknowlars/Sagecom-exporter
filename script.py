#!/usr/bin/env python3
import asyncio
import requests
import speedtest
import time
from ping3 import ping
from datetime import datetime, timedelta
from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
from prometheus_client import Gauge, Info, start_http_server
import os  # For environment variables

# ------------------------------------------------------------------------------
# Environment variables or defaults
# ------------------------------------------------------------------------------
HOST = os.getenv("ROUTER_HOST", "192.168.0.1")
USERNAME = os.getenv("ROUTER_USERNAME", "admin")
PASSWORD = os.getenv("ROUTER_PASSWORD", "MTMF2NXC")
ENCRYPTION_METHOD = EncryptionMethod.SHA512
VALIDATE_SSL_CERT = False

# How often to collect (default 300s = 5 minutes)
COLLECTION_INTERVAL = int(os.getenv("COLLECTION_INTERVAL", "300"))
# Prometheus port
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# ------------------------------------------------------------------------------
# Prometheus Metrics
# ------------------------------------------------------------------------------
# Original metrics
device_uptime_gauge = Gauge('sagemcom_device_uptime_seconds', 'Uptime of the router in seconds')
device_reboot_count_gauge = Gauge('sagemcom_device_reboot_count', 'Number of times the router has rebooted')
connected_devices_gauge = Gauge('sagemcom_connected_devices', 'Number of active devices on the network')

device_info_gauge = Gauge(
    'sagemcom_connected_device_info',
    'Detailed information about each connected device',
    [
        'device_id', 'device_name', 'ip', 'hostname', 'status',
        'interface_type', 'lease_time_remaining', 'layer1_interface',
        'layer3_interface', 'blacklist_status', 'blacklisted_schedule'
    ]
)

device_status_gauge = Gauge(
    'sagemcom_device_status', 'Device active status', ['mac_address', 'name', 'hostname', 'interface']
)
device_lease_gauge = Gauge(
    'sagemcom_device_lease', 'Device DHCP lease details', ['mac_address', 'metric']
)

# Static router info
modem_info = Info('sagemcom_modem_info', 'Static information about the modem')

# Public IP
public_ip_info = Info('public_ip_info', 'Public IP information')

# Speedtest metrics
speedtest_download_gauge = Gauge('internet_speedtest_download_mbps', 'Download speed in Mbps')
speedtest_upload_gauge = Gauge('internet_speedtest_upload_mbps', 'Upload speed in Mbps')
speedtest_ping_gauge = Gauge('internet_speedtest_ping_ms', 'Ping in milliseconds')

# Ping to Google
google_ping_gauge = Gauge('google_ping_ms', 'Ping time to google.com in milliseconds')

# Port mapping gauge
port_mapping_gauge = Gauge(
    'sagemcom_port_mappings',
    'Details of NAT port mappings',
    ['external_port', 'internal_port', 'protocol', 'status']
)

# ------------------------------------------------------------------------------
# NEW Wi-Fi metrics (EXAMPLE)
# ------------------------------------------------------------------------------
wifi_radio_signal_gauge = Gauge(
    'sagemcom_wifi_radio_signal_dbm',
    'Signal strength (dBm) for each Wi-Fi radio',
    ['radio_index']
)
wifi_radio_channel_gauge = Gauge(
    'sagemcom_wifi_radio_channel',
    'Current channel for each Wi-Fi radio',
    ['radio_index']
)

# ------------------------------------------------------------------------------
# Timing controls
# ------------------------------------------------------------------------------
speedtest_interval_seconds = 3600  # Default: run speedtest once per hour
last_speedtest_time = 0
last_pull_time = None
next_pull_time = None

# ------------------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------------------
async def fetch_public_ip():
    """Fetch public IP using ipify."""
    try:
        resp = requests.get('https://api.ipify.org?format=json', timeout=5)
        resp.raise_for_status()
        return resp.json().get('ip')
    except Exception as e:
        print(f"Error fetching public IP: {e}")
        return None

async def run_speedtest():
    """Runs speed test and updates Prometheus metrics."""
    try:
        st = speedtest.Speedtest()
        st.get_best_server()
        download_speed = st.download() / 1_000_000  # Mbps
        upload_speed = st.upload() / 1_000_000      # Mbps
        ping_ms = st.results.ping

        speedtest_download_gauge.set(download_speed)
        speedtest_upload_gauge.set(upload_speed)
        speedtest_ping_gauge.set(ping_ms)

        print(
            f"Speed Test - Download: {download_speed:.2f} Mbps, "
            f"Upload: {upload_speed:.2f} Mbps, "
            f"Ping: {ping_ms:.2f} ms"
        )
    except Exception as e:
        print(f"Error running speed test: {e}")

async def ping_google():
    """Pings google.com and updates result in ms."""
    try:
        ping_time = ping('google.com', timeout=1)
        if ping_time is not None:
            google_ping_gauge.set(ping_time * 1000)
            print(f"Ping to Google: {ping_time * 1000:.2f} ms")
        else:
            google_ping_gauge.set(float('nan'))
    except Exception as e:
        print(f"Error pinging google.com: {e}")
        google_ping_gauge.set(float('nan'))

async def collect_port_mappings(client):
    """
    Collect NAT port mappings using the 'Device/NAT/PortMappings' XPath.
    If your firmware uses different fields (e.g. 'ExternalPort' vs 'external_port'),
    adjust keys below accordingly.
    """
    try:
        port_mappings = await client.get_value_by_xpath("Device/NAT/PortMappings")
        port_mapping_gauge.clear()
        if not port_mappings:
            return

        for mapping in port_mappings:
            # Adjust the dict keys if your device uses different names
            external_port = mapping.get('external_port', 'unknown')
            internal_port = mapping.get('internal_port', 'unknown')
            protocol = mapping.get('protocol', 'unknown')
            enabled = 'active' if mapping.get('enabled', False) else 'inactive'

            port_mapping_gauge.labels(
                external_port=external_port,
                internal_port=internal_port,
                protocol=protocol,
                status=enabled
            ).set(1)
    except Exception as e:
        print(f"Error collecting port mappings: {e}")

# ------------------------------------------------------------------------------
# NEW: Helper function for Wi-Fi stats (EXAMPLE)
# ------------------------------------------------------------------------------
async def collect_wifi_stats(client: SagemcomClient):
    """
    Example: Collect Wi-Fi radio stats from 'Device/WiFi/Radios'.
    You MUST adjust the path/fields to match your router's firmware.
    """
    try:
        wifi_radios = await client.get_value_by_xpath("Device/WiFi/Radios")
        if not wifi_radios:
            print("No Wi-Fi radios found or path not supported.")
            return

        # Clear old values to avoid stale data
        wifi_radio_signal_gauge.clear()
        wifi_radio_channel_gauge.clear()

        # Suppose `wifi_radios` is a list of dicts, each describing a radio
        for i, radio in enumerate(wifi_radios):
            # Adjust field names to match your actual data!
            channel = radio.get("channel", 0)
            signal_dbm = radio.get("signal_strength", 0)

            # Update Prometheus
            wifi_radio_signal_gauge.labels(radio_index=i).set(signal_dbm)
            wifi_radio_channel_gauge.labels(radio_index=i).set(channel)

    except Exception as e:
        print(f"Error collecting Wi-Fi stats: {e}")

# ------------------------------------------------------------------------------
# Main metrics collection
# ------------------------------------------------------------------------------
async def collect_sagemcom_metrics():
    """
    Collects all Sagemcom metrics: device info, DHCP leases, port mappings, etc.
    """
    global last_pull_time, next_pull_time

    async with SagemcomClient(
        HOST,
        USERNAME,
        PASSWORD,
        ENCRYPTION_METHOD,
        verify_ssl=VALIDATE_SSL_CERT
    ) as client:
        try:
            # 1) Login
            await client.login()

            # --------------------------------------------------
            # 2) Original device info (using .get_device_info())
            # --------------------------------------------------
            device_info = await client.get_device_info()
            print(f"Device ID: {device_info.mac_address}")
            print(f"Build Date: {device_info.build_date}")
            print(f"Uptime: {device_info.up_time}")
            print(f"Reboot count: {device_info.reboot_count}")
            print(f"Model Name: {device_info.model_name}")
            print(f"Serial Number: {device_info.serial_number}")
            print(f"Software Version: {device_info.software_version}")

            # Update Prometheus
            device_uptime_gauge.set(device_info.up_time)
            device_reboot_count_gauge.set(device_info.reboot_count)
            modem_info.info({
                'device_id': device_info.mac_address,
                'build_date': device_info.build_date,
                'model_name': device_info.model_name,
                'serial_number': device_info.serial_number,
                'software_version': device_info.software_version
            })

            # --------------------------------------------------
            # 3) DHCP clients / connected devices
            # --------------------------------------------------
            devices = await client.get_hosts()
            active_devices = [d for d in devices if d.active]
            connected_devices_gauge.set(len(active_devices))

            # Clear old device metrics
            device_status_gauge.clear()
            device_lease_gauge.clear()
            device_info_gauge.clear()

            for d in devices:
                # device status (1=active, 0=inactive)
                device_status_gauge.labels(
                    mac_address=d.id,
                    name=d.name,
                    hostname=d.host_name,
                    interface=d.interface_type
                ).set(1 if d.active else 0)

                # lease details
                device_lease_gauge.labels(mac_address=d.id, metric='lease_start').set(d.lease_start)
                device_lease_gauge.labels(mac_address=d.id, metric='lease_duration').set(d.lease_duration)
                device_lease_gauge.labels(mac_address=d.id, metric='lease_remaining').set(d.lease_time_remaining)

                # extended device info
                device_info_gauge.labels(
                    device_id=d.phys_address or "unknown",
                    device_name=d.alias or "unknown",
                    ip=d.ip_address or "unknown",
                    hostname=d.host_name or "unknown",
                    status="Active" if d.active else "Inactive",
                    interface_type=d.interface_type or "unknown",
                    lease_time_remaining=str(d.lease_time_remaining),
                    layer1_interface=d.layer1_interface or "unknown",
                    layer3_interface=d.layer3_interface or "unknown",
                    blacklist_status="True" if d.blacklisted else "False",
                    blacklisted_schedule=str(d.blacklisted_schedule or [])
                ).set(1 if d.active else 0)

            # --------------------------------------------------
            # 4) Port Mappings
            # --------------------------------------------------
            await collect_port_mappings(client)

            # --------------------------------------------------
            # 5) Wi-Fi Stats (NEW)
            # --------------------------------------------------
            # Comment out if not relevant or if your router does not have Wi-Fi
            await collect_wifi_stats(client)

            # --------------------------------------------------
            # 6) Public IP
            # --------------------------------------------------
            public_ip = await fetch_public_ip()
            if public_ip:
                public_ip_info.info({'public_ip': public_ip})

            # Logging of pull times
            last_pull_time = datetime.now()
            next_pull_time = last_pull_time + timedelta(seconds=COLLECTION_INTERVAL)
            print(f"Last metrics pull: {last_pull_time}")
            print(f"Next metrics pull: {next_pull_time}")

        except Exception as ex:
            print(f"An error occurred while retrieving data: {ex}")

# ------------------------------------------------------------------------------
# Loop to periodically collect metrics, ping Google, run Speedtest
# ------------------------------------------------------------------------------
async def update_metrics_loop():
    global last_speedtest_time
    while True:
        # 1) Collect router metrics
        await collect_sagemcom_metrics()

        # 2) Ping Google
        await ping_google()

        # 3) Possibly run Speedtest (e.g. once per hour)
        current_time = time.time()
        if current_time - last_speedtest_time >= speedtest_interval_seconds:
            await run_speedtest()
            last_speedtest_time = current_time

        # Sleep until next iteration
        await asyncio.sleep(COLLECTION_INTERVAL)

# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
if __name__ == '__main__':
    # Start Prometheus server
    start_http_server(SERVER_PORT)
    print(f"Prometheus exporter started on port {SERVER_PORT}.")
    print(f"Scraping every {COLLECTION_INTERVAL} seconds.")

    # Run asyncio event loop
    asyncio.run(update_metrics_loop())
