import socket
import json
import time
import random
import threading
import math


class M5StackMock:
    def __init__(self, listen_port=9000, target_host="127.0.0.1", target_port=9001):
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.running = False
        self.sock = None
        self.counter = 0
        self.start_time = 0.0

    def start(self):
        """M5Stackモックを開始"""
        self.running = True
        self.start_time = time.time()

        # 受信用ソケット
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.listen_port))
        self.sock.settimeout(1.0)

        # 送信用ソケット
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # 受信スレッドを開始
        receive_thread = threading.Thread(target=self.receive_commands)
        receive_thread.daemon = True
        receive_thread.start()

        print("M5Stack Mock started")
        print(f"Listening on port {self.listen_port}")
        print(f"Sending to {self.target_host}:{self.target_port}")
        print("Sending sensor data (motor + IMU)...")

        # センサーデータ送信ループ
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
        """センサーデータ（モーター + IMU）を定期送信"""
        while self.running:
            self.counter += 1

            # Arduino風のタイムスタンプ（ミリ秒）
            current_time = time.time()
            timestamp_ms = int((current_time - self.start_time) * 1000)

            # GM6020モーターフィードバックデータをシミュレート（実際のArduinoコードと同じ変換を適用）
            # 生の機械角度: 0-8191 (14bit)
            mech_angle_raw = random.randint(0, 8191)
            # 度に変換: angle_deg = mech_angle * 360.0f / 8192.0f
            angle_deg = mech_angle_raw * 360.0 / 8192.0

            # 生の回転速度: -32768 to 32767 (rpm)
            speed_raw = random.randint(-1000, 1000)
            # RPMをそのまま使用
            speed_rpm = speed_raw

            # 生のトルク電流: -32768 to 32767
            torque_raw = random.randint(-16384, 16384)
            # アンペアに変換: current_A = torque / 2048.0f
            current_A = torque_raw / 2048.0

            # 温度: 0-255 (°C)
            temp = random.randint(20, 80)

            # IMUデータをシミュレート（M5StickC Plus2風）
            # 時間ベースの振動シミュレーション
            t = current_time * 2  # 周波数調整

            # 加速度データ (m/s^2) - 重力 + 振動
            accel_x = round(0.1 * math.sin(t) + random.uniform(-0.05, 0.05), 3)
            accel_y = round(0.1 * math.cos(t * 1.2) + random.uniform(-0.05, 0.05), 3)
            accel_z = round(
                9.8 + 0.2 * math.sin(t * 0.8) + random.uniform(-0.1, 0.1), 3
            )

            # ジャイロデータ (deg/s) - 小さな回転振動
            gyro_x = round(5.0 * math.sin(t * 1.5) + random.uniform(-2.0, 2.0), 3)
            gyro_y = round(3.0 * math.cos(t * 0.9) + random.uniform(-1.5, 1.5), 3)
            gyro_z = round(2.0 * math.sin(t * 2.1) + random.uniform(-1.0, 1.0), 3)

            # 生のジャイロZ軸データ (より大きな値域でランダム)
            raw_gyro_z = round(
                50.0 * math.sin(t * 0.5) + random.uniform(-20.0, 20.0), 3
            )

            # ArduinoコードのJSON構造に合わせる（変換済みの値を使用）
            sensor_data = {
                "motor": {
                    "current": round(current_A, 3),  # アンペア
                    "angle": round(angle_deg, 3),  # 度
                    "speed": speed_rpm,  # RPM
                    "torque": torque_raw,  # 生の値（Arduinoコードと同じ）
                    "temp": temp,  # 摂氏
                },
                "control": {
                    "target_rpm": random.randint(50, 150),  # 目標RPM
                    "current_rpm": round(
                        speed_rpm + random.uniform(-5.0, 5.0), 1
                    ),  # 現在RPM
                    "output_current": round(
                        current_A + random.uniform(-0.5, 0.5), 2
                    ),  # 出力電流
                    "error": round(random.uniform(-10.0, 10.0), 1),  # エラー
                },
                "accel": {"x": accel_x, "y": accel_y, "z": accel_z},
                "gyro": {"x": gyro_x, "y": gyro_y, "z": gyro_z, "raw_z": raw_gyro_z},
                "timestamp": timestamp_ms,
                "counter": self.counter,
            }

            try:
                message = json.dumps(sensor_data)
                self.send_sock.sendto(
                    message.encode("utf-8"), (self.target_host, self.target_port)
                )

                # 100回に1回、詳細情報を表示
                if self.counter % 100 == 0:
                    print(
                        f"[M5Stack] #{self.counter}: motor_angle={angle_deg:.3f}°, speed={speed_rpm}rpm, temp={temp}°C"
                    )
                    print(
                        f"           accel=({accel_x:.3f}, {accel_y:.3f}, {accel_z:.3f}) m/s²"
                    )
                    print(
                        f"           gyro=({gyro_x:.3f}, {gyro_y:.3f}, {gyro_z:.3f}) deg/s"
                    )
                    print(f"           raw_gyro_z={raw_gyro_z:.3f} deg/s")
                    print(
                        f"           current={current_A:.3f}A, torque_raw={torque_raw}"
                    )
                    # controlデータを取得して表示
                    control_data = sensor_data["control"]
                    print(
                        f"           control: target={control_data['target_rpm']}rpm, current={control_data['current_rpm']}rpm, "
                        f"output={control_data['output_current']}A, error={control_data['error']}"
                    )
                else:
                    # 通常は簡潔な表示
                    print(f"[M5Stack] #{self.counter}: sending sensor data...")

            except Exception as e:
                print(f"[M5Stack] Send error: {e}")

            # 50ms間隔（Arduinoコードの LOOP_INTERVAL に合わせる）
            time.sleep(0.05)

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
            # pingに対してpongを返す（無効化）
            # pong = {"type": "pong", "timestamp": time.time()}
            # message = json.dumps(pong)
            # UDP送信を無効化
            # self.sock.sendto(
            #     message.encode("utf-8"), (self.target_host, self.target_port)
            # )
            print("[M5Stack] 📡 Ping received, pong disabled")

        else:
            print(f"[M5Stack] ❓ Unknown command: {cmd_type}")

    def stop(self):
        """停止"""
        self.running = False
        if self.sock:
            self.sock.close()
        if hasattr(self, "send_sock") and self.send_sock:
            self.send_sock.close()


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
