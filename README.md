# Sagecom-exporter
Promethues exporter for sagecom router based on python-sagemcom-api

A promethues exporter for sagecom routers usually a ISP router, I wanted to see dhcp lease and conncted clients and other information about my home network and ISP router

The exporter is build using python based on another github project "https://github.com/iMicknl/python-sagemcom-api" 

The exporter collect
- Router information - Software version, build, model name, Uptime
- DHCP information - Devices connected or disconnected with Mac address, Hostname, status
- Wifi channel information
- Port mapning - Port forward rules, Internal and external port, protocol, status
- Speedtest information - Download speed and upload speeed
- Ping

  Speedtest runs every hour

  
