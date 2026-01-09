#!/usr/bin/env python3
"""
LocalScholar-Flow Service Health Check Script (Enhanced Compatibility Version)
Logic:
1. MongoDB: TCP port connectivity is sufficient.
2. MinerU: TCP connectivity or any HTTP response (200, 404, 405) indicates successful startup.
3. Hunyuan: Requires /v1/models to return 200 (model weights loaded).
"""

import socket
import sys
import time
import urllib.request
import urllib.error
import json

def check_tcp(host, port, timeout=1):
    """Basic check: is port open"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

def check_http_loose(url):
    """
    Lenient HTTP check (for MinerU)
    As long as the server responds (even 404 Not Found or 405 Method Not Allowed),
    the web service is considered up.
    Only Connection Refused is considered a failure.
    """
    try:
        # Try sending request
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=2) as response:
            return True, f"OK ({response.status})"
    except urllib.error.HTTPError as e:
        # Key: HTTPError (404, 405, 500) means server is connected, just wrong path or method
        # For health check, this represents service is UP
        return True, f"Alive ({e.code})"
    except urllib.error.URLError as e:
        # URLError usually means Connection Refused, service not up yet
        return False, str(e.reason)
    except Exception as e:
        return False, str(e)

def check_llm_ready(url):
    """
    Strict HTTP check (for Hunyuan)
    Must return 200 with data, ensuring model loading is complete.
    """
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200:
                # Try parsing JSON to ensure not empty response
                body = response.read()
                data = json.loads(body)
                if "data" in data or "object" in data:
                    return True, "Ready"
            return False, f"Status {response.status}"
    except urllib.error.HTTPError as e:
        # For LLM, if error (like 503), still loading, not Ready
        return False, f"Loading... ({e.code})"
    except Exception as e:
        return False, "Connecting..."

def main():
    print("=" * 60)
    print("🔍 Service Status Deep Detection")
    print("=" * 60)

    # Configuration
    services = [
        {
            "name": "MongoDB",
            "type": "tcp",
            "host": "localhost",
            "port": 27016
        },
        {
            "name": "MinerU (PDF Parser)",
            "type": "http_loose", # Port open, web service responsive = good
            "url": "http://localhost:8000/",
            # Backup check: if root path fails, can also check docs
            # "url": "http://localhost:8000/docs"
        },
        {
            "name": "Hunyuan (Translation Model)",
            "type": "llm_strict", # Must wait for model loading complete
            "url": "http://localhost:8001/v1/models"
        }
    ]

    max_retries = 60 # 5 minutes (60 * 5s)
    interval = 5

    # Initialize status
    status_map = {svc["name"]: False for svc in services}

    for i in range(max_retries):
        all_up = True
        sys.stdout.write(f"\r⏳ [Check {i+1}] ")

        status_output = []

        for svc in services:
            name = svc["name"]

            # If already up, no need to check repeatedly (unless real-time monitoring)
            if status_map[name]:
                status_output.append(f"✅ {name}")
                continue

            is_up = False
            msg = ""

            if svc["type"] == "tcp":
                is_up = check_tcp(svc["host"], svc["port"])

            elif svc["type"] == "http_loose":
                is_up, msg = check_http_loose(svc["url"])
                # If loose check fails, try TCP as fallback
                if not is_up and "localhost" in svc["url"]:
                    port = int(svc["url"].split(":")[-1].split("/")[0])
                    if check_tcp("localhost", port):
                        is_up = True
                        msg = "TCP OK (HTTP Fail)"

            elif svc["type"] == "llm_strict":
                is_up, msg = check_llm_ready(svc["url"])

            if is_up:
                status_map[name] = True
                status_output.append(f"✅ {name}")
            else:
                all_up = False
                # Only show detailed status for services not yet started
                short_msg = msg if msg else "Waiting"
                status_output.append(f"❌ {name}({short_msg})")

        # Print current round status
        print(" | ".join(status_output))

        if all_up:
            print("\n" + "=" * 60)
            print("🚀 All services passed checks! System ready.")
            print("=" * 60)
            sys.exit(0)

        time.sleep(interval)

    print("\n❌ Timeout: Some services failed to become ready.")
    print("Suggestion: Manually run 'docker compose logs -f' to view detailed logs.")
    sys.exit(1)

if __name__ == "__main__":
    main()
