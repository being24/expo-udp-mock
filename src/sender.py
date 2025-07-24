import socket
import json
import time
import random
import threading


class M5StackMock:
    def __init__(self, listen_port=12345, target_host="127.0.0.1", target_port=12346):
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.running = False
        self.sock = None

    def start(self):
        """M5Stackモックを開始"""
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.listen_port))
        self.sock.settimeout(1.0)

        # 受信スレッドを開始
        receive_thread = threading.Thread(target=self.receive_commands)
        receive_thread.daemon = True
        receive_thread.start()

        print("M5Stack Mock started")
        print(f"Listening on port {self.listen_port}")
        print(f"Sending to {self.target_host}:{self.target_port}")
        print("Sending motor data...")

        # モーターデータ送信ループ
        self.send_sensor_data()

    def receive_commands(self):
        """コマンド受信"""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                message = data.decode("utf-8")
                print(f"[M5Stack] Received command from {addr}: {message}")

                try:
                    command = json.loads(message)
                    self.handle_command(command)
                except json.JSONDecodeError:
                    print(f"[M5Stack] Invalid JSON: {message}")

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[M5Stack] Receive error: {e}")

    def send_sensor_data(self):
        """モーターデータを定期送信"""
        counter = 0
        while self.running:
            # モックモーターデータ（例の値に近い範囲で生成）
            motor_data = {
                "can_id": "0x205",
                "angle_raw": random.randint(2048, 6144),  # 4096付近の値
                "angle_deg": round(random.uniform(90.0, 270.0), 1),  # 180度付近
                "speed_rpm": random.randint(60, 180),  # 120rpm付近
                "current_raw": random.randint(6144, 10240),  # 8192付近
                "current_a": round(random.uniform(1.0, 2.0), 1),  # 1.5A付近
                "torque_nm": round(random.uniform(0.8, 1.4), 4),  # 1.1115Nm付近
                "temperature_c": random.randint(35, 50),  # 42度付近
            }

            try:
                message = json.dumps(motor_data)
                self.sock.sendto(
                    message.encode("utf-8"), (self.target_host, self.target_port)
                )
                print(
                    f"[M5Stack] Sent #{counter}: angle={motor_data['angle_deg']}°, speed={motor_data['speed_rpm']}rpm, temp={motor_data['temperature_c']}°C"
                )
                counter += 1
            except Exception as e:
                print(f"[M5Stack] Send error: {e}")

            time.sleep(1.0)  # 1秒間隔

    def handle_command(self, command):
        """受信したコマンドを処理"""
        cmd_type = command.get("type")

        if cmd_type == "led_control":
            color = command.get("color", "white")
            brightness = command.get("brightness", 100)
            print(f"[M5Stack] 💡 LED: {color} (brightness: {brightness}%)")

        elif cmd_type == "servo_control":
            angle = command.get("angle", 0)
            print(f"[M5Stack] 🔄 Servo: {angle}°")

        elif cmd_type == "display_text":
            text = command.get("text", "")
            print(f"[M5Stack] 📺 Display: '{text}'")

        elif cmd_type == "ping":
            # pingに対してpongを返す
            pong = {"type": "pong", "timestamp": time.time()}
            message = json.dumps(pong)
            self.sock.sendto(
                message.encode("utf-8"), (self.target_host, self.target_port)
            )
            print(f"[M5Stack] 📡 Ping received, sent pong")

        else:
            print(f"[M5Stack] ❓ Unknown command: {cmd_type}")

    def stop(self):
        """停止"""
        self.running = False
        if self.sock:
            self.sock.close()


def main():
    print("M5Stack UDP Mock - Starting...")

    m5stack = M5StackMock()

    try:
        m5stack.start()

    except KeyboardInterrupt:
        print("\n[M5Stack] Stopping...")
        m5stack.stop()
        print("[M5Stack] Stopped.")


if __name__ == "__main__":
    main()
