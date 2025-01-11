# Sagecom-exporter
Promethues exporter for sagecom router based on python-sagemcom-api

A promethues exporter for sagecom routers usually a ISP router, I wanted to see dhcp lease and conncted clients and other information about my home network and ISP router

The exporter is build using python based on another github project "https://github.com/iMicknl/python-sagemcom-api" 

Grafana Dashboard : 

The exporter collect
- Router information - Software version, build, model name, Uptime
- DHCP information - Devices connected or disconnected with Mac address, Hostname, status
- Wifi channel information
- Port mapning - Port forward rules, Internal and external port, protocol, status
- Speedtest information - Download speed and upload speeed
- Ping


You can build the container locally if you clone this repo and run "docker build -t sagemcom-exporter ."

I have also uploaded a Container image to this repo and docker compose file


Yaml::loadToConfig(config_path('Docker-compose.yml'), 'Docker-compose.yml');




  
