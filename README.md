# Syslog Listener & NAT Mapping Monitor

A Python-based network monitoring service that listens for Cisco syslog messages, extracts structured event information, and forwards notifications to a backend API. It also connects to a Cisco IOS router over SSH to retrieve static TCP NAT mappings and synchronize them with the backend.

## Features

- **UDP Syslog Listener:** Receives syslog messages on port `514`.
- **Syslog Parser:** Extracts priority, timestamp, facility, severity, message tag, message text, and device IP address.
- **Backend Integration:** Sends parsed notifications to the Express API using HTTP POST requests.
- **Router SSH Connection:** Uses Netmiko to connect to a Cisco IOS router and execute `show running-config`.
- **NAT Configuration Parser:** Identifies static TCP NAT entries from the router's running configuration.
- **Automatic NAT Synchronization:** Creates or updates NAT mapping records through the backend API.
- **Background Monitoring:** Checks the router's NAT configuration every 30 minutes.
- **Concurrent Execution:** Runs the router monitoring task in a background thread while the syslog listener remains active.

## Technologies

- Python 3
- Netmiko
- Requests
- Cisco IOS
- UDP sockets
- REST API

## Requirements

- Python 3 installed on the host machine.
- A Cisco IOS router or compatible lab router.
- SSH connectivity to the router.
- A running Express backend API.
- Network connectivity between Cisco devices, the Python service, and the backend.

## Installation

Install the required Python packages:

```bash
pip install requests netmiko
```

The `socket`, `re`, `threading`, and `time` modules are included with Python.

## Configuration

### Backend endpoints

Update the API URLs in the script to match your backend deployment:

```python
NOTIFICATION_URL = "http://localhost:3000/api/v1/notification"
NAT_MAPPING_URL = "http://localhost:3000/api/v1/natmapping"
```

### Router connection

Configure the router connection details in the `router` dictionary:

```python
router = {
    "device_type": "cisco_ios",
    "host": "192.168.75.139",
    "port": 22,
    "username": "admin",
    "password": "YOUR_ROUTER_PASSWORD",
}
```

Replace these example settings with the correct values for your lab. Do not publish real router credentials in a public repository.

## How It Works

### 1. Syslog collection

The application creates a UDP socket bound to `0.0.0.0:514` and waits for incoming syslog datagrams.

When a message arrives, the application:

1. Reads the message and its UDP source address.
2. Decodes the raw syslog message.
3. Extracts the router IP address where possible.
4. Parses the message into structured fields.
5. Sends the parsed notification to the backend.

### 2. Syslog parsing

The `parse_syslog()` function extracts the following fields:

| Field | Description |
|---|---|
| `priority` | Syslog priority value |
| `timestamp` | Timestamp extracted from the message |
| `facility` | Facility identifier, such as `LINK` |
| `severity` | Syslog severity number |
| `msg_tag` | Message identifier, such as `UPDOWN` |
| `msg_text` | Main message content |
| `raw` | Original syslog message |
| `ipAddress` | Device IP extracted from the message, with UDP source IP as fallback |
| `status` | Initial status set by the script |

### 3. Notification forwarding

Parsed messages are sent to the backend through:

```text
POST /api/v1/notification
```

The request sends the parsed event as a JSON payload.

### 4. NAT mapping discovery

The `get_nat_details()` function connects to the router through SSH and executes:

```text
show running-config
```

It searches for static TCP NAT entries matching the format:

```text
ip nat inside source static tcp 192.168.1.2 22 interface FastEthernet0/0 2222
```

For a matching entry, the script extracts the inside IP address, inside port, interface, and outside port.

### 5. NAT synchronization

The `save_nat_mapping()` function checks existing mappings through:

```text
GET /api/v1/natmapping
```

It searches for a mapping with the same `sourceIp`.

- If a mapping exists, the script sends a `PUT` request to update it.
- If no mapping exists, the script sends a `POST` request to create it.

The payload contains:

```json
{
  "sourceIp": "192.168.1.2",
  "natHost": "192.168.75.139",
  "natPort": 2222
}
```

These are illustrative values based on the code's payload format.

### 6. Periodic monitoring

The `router_monitor()` function runs in a daemon thread. It retrieves the router's NAT configuration, synchronizes the discovered mappings, and waits 30 minutes before repeating the process.

## Running the Application

Save the Python script as `main.py` and run:

```bash
python main.py
```

If your environment uses `python3`, run:

```bash
python3 main.py
```

The script starts the router NAT monitor in the background and then starts the syslog listener.

On systems where port `514` requires elevated privileges, configure the minimum necessary permissions or use a controlled port-forwarding arrangement.

## Network Setup

Before running the service, ensure that:

- The router is reachable over SSH.
- Cisco devices are configured to send syslog messages to the listener host.
- UDP port `514` is allowed by the relevant firewall rules.
- The Express backend is running and reachable.
- The backend accepts the notification and NAT mapping payload formats used by the script.
- The router has static TCP NAT entries matching the parser's expected format.

## Limitations

- The NAT parser recognizes only the static TCP NAT command format defined by its regular expression.
- The IP extraction fallback may select an address that is not the actual device IP if the message format differs.
- Syslog messages are processed in the listener loop, so a slow API request can delay handling subsequent messages.
- NAT create/update requests print response status codes but do not fully validate successful completion.
- The service uses traditional UDP syslog, which does not provide message authentication by itself.

## Security Considerations

- Store router passwords and other secrets in environment variables rather than source code.
- Restrict access to the syslog listener to trusted network devices where practical.
- Protect the backend API with suitable authentication and authorization.
- Restrict SSH access to authorized devices and users.
- Avoid exposing management services to untrusted networks.

## Project Purpose

This service bridges network-device monitoring and backend event management by collecting syslog messages, converting them into structured notifications, and keeping the application's NAT mapping records synchronized with the Cisco router's configuration.
