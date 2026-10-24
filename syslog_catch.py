import socket
import requests
import re
import threading
import time

from netmiko import ConnectHandler


# =========================================================
# BACKEND URLS
# =========================================================

NOTIFICATION_URL = (
    "http://localhost:3000/api/v1/notification"
)

NAT_MAPPING_URL = (
    "http://localhost:3000/api/v1/natmapping"
)


# =========================================================
# ROUTER CONFIGURATION
# =========================================================

router = {
    "device_type": "cisco_ios",
    "host": "192.168.75.139",
    "port": 22,
    "username": "admin",
    "password": "ccna",
}


# =========================================================
# GET NAT CONFIGURATION FROM ROUTER
# =========================================================

def get_nat_details():

    try:

        print("\n========================================")
        print("Connecting to router...")
        print("Router:", router["host"])
        print("Port  :", router["port"])
        print("========================================")

        ssh = ConnectHandler(**router)

        print("Connected to router.")

        # =================================================
        # GET RUNNING CONFIGURATION
        # =================================================

        output = ssh.send_command(
            "show running-config"
        )

        ssh.disconnect()

        print("Disconnected from router.")

        # =================================================
        # NAT REGEX
        #
        # Example:
        #
        # ip nat inside source static tcp
        # 192.168.1.2 22 interface FastEthernet0/0 2222
        #
        # Result:
        #
        # inside IP    = 192.168.1.2
        # inside port  = 22
        # interface    = FastEthernet0/0
        # outside port = 2222
        # =================================================

        pattern = re.compile(
            r"ip nat inside source static tcp "
            r"(\d+\.\d+\.\d+\.\d+)\s+"
            r"(\d+)\s+"
            r"interface\s+(\S+)\s+"
            r"(\d+)"
        )

        nat_entries = []

        # =================================================
        # FIND NAT ENTRIES
        # =================================================

        for line in output.splitlines():

            line = line.strip()

            match = pattern.search(line)

            if not match:
                continue

            inside_ip = match.group(1)

            inside_port = int(
                match.group(2)
            )

            interface = match.group(3)

            outside_port = int(
                match.group(4)
            )

            entry = {

                "insideIp": inside_ip,

                "insidePort": inside_port,

                "interface": interface,

                "outsidePort": outside_port,

                "insideAddress":
                    f"{inside_ip}:{inside_port}",

                "outsideAddress":
                    f"{router['host']}:{outside_port}",
            }

            nat_entries.append(entry)

        # =================================================
        # DISPLAY NAT MAPPINGS
        # =================================================

        print("\nNAT MAPPINGS")
        print("========================================")

        if not nat_entries:

            print(
                "No static TCP NAT mappings found."
            )

        else:

            for entry in nat_entries:

                print(
                    f"{entry['insideAddress']} "
                    f"-> "
                    f"{entry['outsideAddress']}"
                )

        print("========================================")

        return nat_entries

    except Exception as e:

        print("\nRouter connection error:")
        print(e)

        return []


# =========================================================
# SAVE / UPDATE NAT MAPPING
# =========================================================

def save_nat_mapping(entry):

    try:

        source_ip = entry["insideIp"]

        # =================================================
        # DATA EXPECTED BY BACKEND
        # =================================================

        payload = {

            "sourceIp": source_ip,

            "natHost": router["host"],

            "natPort": entry["outsidePort"],
        }

        # =================================================
        # GET EXISTING NAT MAPPINGS
        # =================================================

        response = requests.get(
            NAT_MAPPING_URL,
            timeout=5
        )

        if response.status_code != 200:

            print(
                "Failed to get NAT mappings:",
                response.status_code
            )

            return

        result = response.json()

        mappings = result.get(
            "data",
            []
        )

        existing = None

        # =================================================
        # FIND EXISTING SOURCE IP
        # =================================================

        for mapping in mappings:

            if mapping.get(
                "sourceIp"
            ) == source_ip:

                existing = mapping

                break

        # =================================================
        # UPDATE EXISTING MAPPING
        # =================================================

        if existing:

            mapping_id = existing.get(
                "_id"
            )

            update_url = (
                f"{NAT_MAPPING_URL}/{mapping_id}"
            )

            update_response = requests.put(
                update_url,
                json=payload,
                timeout=5
            )

            print(
                f"NAT updated: "
                f"{source_ip} -> "
                f"{router['host']}:{entry['outsidePort']}"
            )

            print(
                "Status:",
                update_response.status_code
            )

        # =================================================
        # CREATE NEW MAPPING
        # =================================================

        else:

            create_response = requests.post(
                NAT_MAPPING_URL,
                json=payload,
                timeout=5
            )

            print(
                f"NAT created: "
                f"{source_ip} -> "
                f"{router['host']}:{entry['outsidePort']}"
            )

            print(
                "Status:",
                create_response.status_code
            )

    except requests.exceptions.RequestException as e:

        print(
            "NAT backend error:",
            e
        )

    except Exception as e:

        print(
            "NAT save error:",
            e
        )


# =========================================================
# SAVE ALL NAT MAPPINGS
# =========================================================

def save_nat_mappings(nat_entries):

    print(
        "\nSaving NAT mappings to backend..."
    )

    for entry in nat_entries:

        save_nat_mapping(
            entry
        )


# =========================================================
# RUN ROUTER CHECK EVERY 30 MINUTES
# =========================================================

def router_monitor():

    while True:

        try:

            print("\n")
            print("########################################")
            print("Running router NAT check")
            print("########################################")

            # =================================================
            # GET NAT CONFIGURATION
            # =================================================

            nat_details = get_nat_details()

            # =================================================
            # SAVE / UPDATE BACKEND
            # =================================================

            save_nat_mappings(
                nat_details
            )

            print(
                "Found",
                len(nat_details),
                "NAT mappings."
            )

        except Exception as e:

            print(
                "Router monitor error:",
                e
            )

        # =================================================
        # WAIT 30 MINUTES
        # =================================================

        print(
            "\nNext router check in 30 minutes..."
        )

        time.sleep(
            30 * 60
        )


# =========================================================
# EXTRACT ROUTER IP FROM SYSLOG MESSAGE
# =========================================================

def extract_router_ip(data):

    """
    Extracts the router/device IP from the syslog message.

    Example input:

    <187>25: 192.168.6.1: *Mar 1 00:44:52.963:
    %LINK-3-UPDOWN: Interface FastEthernet0/1,
    changed state to up

    Returns:

    192.168.6.1
    """

    # =====================================================
    # EXPECTED CISCO SYSLOG FORMAT
    #
    # <PRI>SEQUENCE: IP:
    #
    # Example:
    #
    # <187>25: 192.168.6.1:
    # =====================================================

    pattern = re.compile(
        r"<\d+>\d+:\s+"
        r"(\d+\.\d+\.\d+\.\d+):"
    )

    match = pattern.search(data)

    if match:

        return match.group(1)

    # =====================================================
    # FALLBACK
    #
    # Some Cisco syslog formats may not contain the IP
    # in exactly the same position.
    # =====================================================

    fallback_pattern = re.compile(
        r"\b"
        r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
        r"\b"
    )

    match = fallback_pattern.search(data)

    if match:

        return match.group(1)

    return None


# =========================================================
# PARSE SYSLOG
# =========================================================

def parse_syslog(
    data,
    source_ip,
    source_port
):

    # =====================================================
    # DEFAULT RESULT
    # =====================================================

    result = {

        "priority": "-",

        "timestamp": "-",

        "facility": "-",

        "severity": "-",

        "msg_tag": "-",

        "msg_text": "-",

        "raw": data,

        # This will contain the actual router IP
        # extracted from the syslog message.
        "ipAddress": "-",

        "status": "not complete",
    }

    # =====================================================
    # ROUTER IP
    # =====================================================

    router_ip = extract_router_ip(
        data
    )

    if router_ip:

        result["ipAddress"] = router_ip

    else:

        # =================================================
        # FALLBACK TO UDP SOURCE IP
        # =================================================

        result["ipAddress"] = source_ip

    # =====================================================
    # PRIORITY
    # =====================================================

    priority_match = re.search(
        r"<(\d+)>",
        data
    )

    if priority_match:

        result["priority"] = int(
            priority_match.group(1)
        )

    # =====================================================
    # TIMESTAMP
    #
    # Example:
    #
    # *Mar 1 00:44:52.963:
    # =====================================================

    timestamp_match = re.search(
        r"\*(.*?):",
        data
    )

    if timestamp_match:

        result["timestamp"] = (
            timestamp_match.group(1).strip()
        )

    # =====================================================
    # FACILITY
    #
    # Example:
    #
    # %LINK-3-UPDOWN
    #
    # Result:
    #
    # LINK
    # =====================================================

    facility_match = re.search(
        r"%([A-Z]+)-",
        data
    )

    if facility_match:

        result["facility"] = (
            facility_match.group(1)
        )

    # =====================================================
    # SEVERITY
    #
    # Example:
    #
    # %LINK-3-UPDOWN
    #
    # Result:
    #
    # 3
    # =====================================================

    severity_match = re.search(
        r"%[A-Z]+-(\d)-",
        data
    )

    if severity_match:

        result["severity"] = int(
            severity_match.group(1)
        )

    # =====================================================
    # MESSAGE TAG
    #
    # Example:
    #
    # %LINK-3-UPDOWN:
    #
    # Result:
    #
    # UPDOWN
    # =====================================================

    tag_match = re.search(
        r"%[A-Z]+-\d+-([A-Za-z0-9_]+):",
        data
    )

    if tag_match:

        result["msg_tag"] = (
            tag_match.group(1)
        )

    # =====================================================
    # MESSAGE TEXT
    #
    # Example:
    #
    # Interface FastEthernet0/1,
    # changed state to up
    # =====================================================

    message_match = re.search(
        r"%[A-Z]+-\d+-[A-Za-z0-9_]+:\s*(.*)",
        data
    )

    if message_match:

        result["msg_text"] = (
            message_match.group(1).strip()
        )

    # =====================================================
    # RETURN PARSED RESULT
    # =====================================================

    return result


# =========================================================
# SEND SYSLOG TO BACKEND
# =========================================================

def send_to_backend(payload):

    try:

        response = requests.post(
            NOTIFICATION_URL,
            json=payload,
            timeout=5
        )

        print("\nBackend response")
        print("-------------------------------")

        print(
            "Status:",
            response.status_code
        )

        print(
            "Response:",
            response.text
        )

        print("-------------------------------")

    except requests.exceptions.RequestException as e:

        print(
            "Send error:",
            e
        )


# =========================================================
# SYSLOG LISTENER
# =========================================================

def open_socket():

    HOST = "0.0.0.0"

    PORT = 514

    # =====================================================
    # CREATE UDP SOCKET
    # =====================================================

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    # =====================================================
    # ALLOW SOCKET REUSE
    # =====================================================

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    # =====================================================
    # BIND
    # =====================================================

    server.bind(
        (HOST, PORT)
    )

    print(
        f"\nSyslog listening on "
        f"{HOST}:{PORT} ..."
    )

    print(
        "Waiting for Cisco syslog messages..."
    )

    # =====================================================
    # RECEIVE SYSLOG
    # =====================================================

    while True:

        try:

            data, addr = server.recvfrom(
                4096
            )

            # =================================================
            # UDP SOURCE INFORMATION
            # =================================================

            source_ip = addr[0]

            source_port = addr[1]

            source_address = (
                f"{source_ip}:{source_port}"
            )

            # =================================================
            # DECODE MESSAGE
            # =================================================

            log = data.decode(
                errors="ignore"
            ).strip()

            # =================================================
            # DISPLAY RAW SYSLOG
            # =================================================

            print(
                "\n========================================"
            )

            print(
                "SYSLOG RECEIVED"
            )

            print(
                "UDP Source      :",
                source_address
            )

            print(
                "UDP Source IP   :",
                source_ip
            )

            print(
                "UDP Source Port :",
                source_port
            )

            print(
                "Message         :",
                log
            )

            print(
                "========================================"
            )

            # =================================================
            # EXTRACT ACTUAL ROUTER IP
            # =================================================

            router_ip = extract_router_ip(
                log
            )

            print(
                "Router IP       :",
                router_ip
            )

            # =================================================
            # PARSE SYSLOG
            # =================================================

            parsed = parse_syslog(
                log,
                source_ip,
                source_port
            )

            # =================================================
            # DISPLAY PARSED DATA
            # =================================================

            print(
                "\nParsed Syslog:"
            )

            print(
                "Priority        :",
                parsed["priority"]
            )

            print(
                "Timestamp       :",
                parsed["timestamp"]
            )

            print(
                "Facility        :",
                parsed["facility"]
            )

            print(
                "Severity        :",
                parsed["severity"]
            )

            print(
                "Message Tag     :",
                parsed["msg_tag"]
            )

            print(
                "Message         :",
                parsed["msg_text"]
            )

            print(
                "Router IP       :",
                parsed["ipAddress"]
            )

            print(
                "Status          :",
                parsed["status"]
            )

            print(
                "========================================"
            )

            print(
                "Sending to backend..."
            )

            # =================================================
            # SEND TO BACKEND
            # =================================================

            send_to_backend(
                parsed
            )

        except Exception as e:

            print(
                "\nSyslog listener error:"
            )

            print(e)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    print(
        "\n========================================"
    )

    print(
        "SYSLOG MONITORING SYSTEM"
    )

    print(
        "========================================"
    )

    # =====================================================
    # START ROUTER NAT MONITOR
    # =====================================================

    router_thread = threading.Thread(
        target=router_monitor,
        daemon=True
    )

    router_thread.start()

    print(
        "Router NAT monitor started."
    )

    # =====================================================
    # START SYSLOG LISTENER
    # =====================================================

    open_socket()