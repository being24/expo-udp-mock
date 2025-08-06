import socket
import json
import time
import random

SEND_PORT = 8800
SEND_HOST = "127.0.0.1"

BASE_DATA = {"ax": 0.02, "ay": 0.015, "az": -0.031, "pressure": 8500}


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"Sending to {SEND_HOST}:{SEND_PORT}")
    try:
        while True:
            data = {
                "ax": BASE_DATA["ax"] + random.uniform(-0.01, 0.01),
                "ay": BASE_DATA["ay"] + random.uniform(-0.01, 0.01),
                "az": BASE_DATA["az"] + random.uniform(-0.01, 0.01),
                "pressure": BASE_DATA["pressure"] + random.randint(-100, 100),
            }
            message = json.dumps(data)
            sock.sendto(message.encode("utf-8"), (SEND_HOST, SEND_PORT))
            print(f"Sent: {message}")
            time.sleep(0.1)  # 100ms間隔
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
