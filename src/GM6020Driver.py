import can
import struct
import time
import json
import math
from typing import Dict, Optional, Any


class PIDController:
    def __init__(self, kp=1.0, ki=0.1, kd=0.01, output_limit=16384):
        """
        PIDコントローラー

        Args:
            kp: 比例ゲイン
            ki: 積分ゲイン
            kd: 微分ゲイン
            output_limit: 出力制限値
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limit = output_limit

        self.prev_error = 0.0
        self.integral = 0.0
        self.prev_time = None

    def update(self, setpoint, current_value, dt=None):
        """
        PID制御値を計算

        Args:
            setpoint: 目標値
            current_value: 現在値
            dt: 時間差分（Noneの場合は自動計算）

        Returns:
            制御出力
        """
        current_time = time.time()

        if self.prev_time is None:
            self.prev_time = current_time
            return 0.0

        if dt is None:
            dt = current_time - self.prev_time

        if dt <= 0:
            return 0.0

        # 誤差計算
        error = setpoint - current_value

        # 比例項
        proportional = self.kp * error

        # 積分項
        self.integral += error * dt
        integral_term = self.ki * self.integral

        # 微分項
        derivative = (error - self.prev_error) / dt
        derivative_term = self.kd * derivative

        # PID出力
        output = proportional + integral_term + derivative_term

        # 出力制限
        output = max(-self.output_limit, min(self.output_limit, output))

        # 次回のために保存
        self.prev_error = error
        self.prev_time = current_time

        return int(output)

    def reset(self):
        """PIDコントローラーをリセット"""
        self.prev_error = 0.0
        self.integral = 0.0
        self.prev_time = None


class GM6020Driver:
    def __init__(self, channel="can0", interface="socketcan"):
        """
        GM6020モーター受信クラスの初期化

        Args:
            channel: CANチャンネル (デフォルト: "can0")
            interface: CANインターフェース (デフォルト: "socketcan")
        """
        self.channel = channel
        self.interface = interface
        self.bus: Optional[Any] = None
        self.running = False
        self.latest_feedback: Optional[Dict] = None
        self.target_speed = 0.0  # 目標速度 (rpm)
        self.speed_controller = PIDController(kp=2.0, ki=0.5, kd=0.1)

    def connect(self) -> bool:
        """CANバスに接続"""
        try:
            self.bus = can.interface.Bus(channel=self.channel, interface=self.interface)
            print(f"CANバス接続成功 - {self.channel}")
            return True
        except Exception as e:
            print(f"CAN接続エラー: {e}")
            return False

    def disconnect(self):
        """CANバス接続を切断"""
        if self.bus:
            self.bus.shutdown()
            self.bus = None
            print("CAN接続を切断しました")

    @staticmethod
    def current_to_torque_value(current_a: float) -> int:
        """
        電流値(A)をGM6020のトルク制御値に変換
        current_a: -3.0〜+3.0A
        戻り値: -16384〜+16384の整数
        """
        current_a = max(-3.0, min(3.0, current_a))  # 範囲制限
        return int(current_a * 16384 / 3.0)

    @staticmethod
    def torque_value_to_current(torque_value: int) -> float:
        """
        GM6020のトルク制御値を電流値(A)に変換
        torque_value: -16384〜+16384の整数
        戻り値: -3.0〜+3.0A
        """
        return torque_value * 3.0 / 16384

    def send_voltage_command(self, voltage: float):
        """
        GM6020に電圧制御コマンドを送信
        voltage: -25000〜+25000の整数（0で停止）
        ID=1のモーターに対応（0x1FFに送信）
        """
        if not self.bus:
            print("CANバスに接続されていません")
            return False

        voltage = max(-25000, min(25000, voltage))  # 範囲制限
        v_bytes = struct.pack(">h", voltage)  # big-endian 2バイト

        # 4モーター分のスロットあり：ID=1はByte[0-1]
        data = v_bytes + b"\x00\x00\x00\x00\x00\x00"  # ID=1のみ操作
        msg = can.Message(arbitration_id=0x1FF, data=data, is_extended_id=False)
        self.bus.send(msg)
        print(f"送信: voltage={voltage}")
        return True

    def send_torque_command(self, torque: int):
        """
        GM6020にトルク制御コマンドを送信
        torque: -16384〜+16384の整数（0で停止）
        対応する最大トルク電流範囲: -3A〜0〜3A
        ID=1のモーターに対応（0x1FFに送信）
        """
        if not self.bus:
            print("CANバスに接続されていません")
            return False

        torque = max(-16384, min(16384, torque))  # 範囲制限
        t_bytes = struct.pack(">h", torque)  # big-endian 2バイト

        # 4モーター分のスロットあり：ID=1はByte[0-1]
        data = t_bytes + b"\x00\x00\x00\x00\x00\x00"  # ID=1のみ操作
        msg = can.Message(arbitration_id=0x1FF, data=data, is_extended_id=False)
        self.bus.send(msg)
        print(f"送信: torque={torque}")
        return True

    def parse_gm6020_feedback(self, msg: can.Message) -> Dict:
        """
        GM6020フィードバックメッセージを解析

        Args:
            msg: CANメッセージ

        Returns:
            解析されたモーターデータの辞書
        """
        if len(msg.data) < 7:
            return {}

        try:
            angle_raw = struct.unpack(">H", msg.data[0:2])[0]  # Big-endian
            speed_rpm = struct.unpack(">h", msg.data[2:4])[0]  # signed short
            current_raw = struct.unpack(">h", msg.data[4:6])[0]  # signed short
            temperature = msg.data[6]  # unsigned byte

            angle_deg = (angle_raw / 8192.0) * 360.0
            current_a = current_raw / 5461.33  # ≒ ±3Aレンジ（16384/3.0）

            return {
                "can_id": f"0x{msg.arbitration_id:X}",
                "angle_raw": angle_raw,
                "angle_deg": round(angle_deg, 2),
                "speed_rpm": speed_rpm,
                "current_raw": current_raw,
                "current_a": round(current_a, 2),
                "temperature_c": temperature,
                "timestamp": time.time(),
            }

        except Exception as e:
            print(f"解析エラー: {e}")
            return {}

    def receive_feedback(self, timeout=0.01) -> Optional[Dict]:
        """
        フィードバックメッセージを受信（ノンブロッキング）

        Args:
            timeout: 受信タイムアウト（秒）

        Returns:
            フィードバックデータまたはNone
        """
        if not self.bus:
            return None

        try:
            msg = self.bus.recv(timeout=timeout)

            if msg and 0x205 <= msg.arbitration_id <= 0x20B:
                data = self.parse_gm6020_feedback(msg)
                if data:
                    self.latest_feedback = data
                    return data
        except Exception:
            pass  # タイムアウトやエラーは無視

        return None

    def get_latest_feedback(self) -> Optional[Dict]:
        """
        最新のフィードバックデータを取得

        Returns:
            最新のフィードバックデータ（辞書）またはNone
        """
        return self.latest_feedback

    def listen_for_feedback(self, timeout=1.0):
        """
        GM6020フィードバックメッセージを受信・表示

        Args:
            timeout: 受信タイムアウト（秒）
        """
        if not self.bus:
            print("CANバスに接続されていません")
            return

        print("RoboMaster GM6020 フィードバック受信中... (Ctrl+Cで終了)")
        print("=" * 60)

        self.running = True
        message_count = 0

        try:
            while self.running:
                msg = self.bus.recv(timeout=timeout)

                if msg is None:
                    continue

                # GM6020のフィードバックIDをチェック (0x205-0x20B)
                if 0x205 <= msg.arbitration_id <= 0x20B:
                    message_count += 1
                    data = self.parse_gm6020_feedback(msg)

                    if data:
                        print(f"[#{message_count}] GM6020 フィードバック:")
                        print(json.dumps(data, indent=2))
                        print("-" * 50)

        except KeyboardInterrupt:
            print("\n受信を停止します...")
        except Exception as e:
            print(f"受信エラー: {e}")
        finally:
            self.running = False


if __name__ == "__main__":
    print("GM6020 CAN Driver - 速度制御")
    print("=" * 50)

    # GM6020ドライバーを初期化
    driver = GM6020Driver()

    try:
        # CANバスに接続
        if driver.connect():
            # 速度を指定して、トルク制御
            driver.target_speed = 30  # 目標速度 (rpm)
            driver.speed_controller = PIDController(kp=2.0, ki=0.5, kd=0.1)
            while True:
                current_feedback = driver.receive_feedback(timeout=0.1)
                if current_feedback:
                    print(f"最新フィードバック: {current_feedback['speed_rpm']} rpm, ")
                time.sleep(0.1)

        else:
            print("CANバスへの接続に失敗しました")

    except Exception as e:
        print(f"エラー: {e}")
    finally:
        driver.disconnect()
