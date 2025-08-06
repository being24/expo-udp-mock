import asyncio
import json
import queue
import socket
import threading
import time
from collections import deque

import dearpygui.dearpygui as dpg

from throw_data_manager import ThrowDataManager


class SensorDataGUI:
    def __init__(self, listen_port=9001):
        self.listen_port = listen_port
        self.running = False
        self.sock = None

        # UDP送信用の設定
        self.send_host = "127.0.0.1"
        self.send_port = 9000
        self.send_sock = None

        # サインモード用の設定
        self.sine_mode_enabled = False
        self.sine_amplitude = 100
        self.sine_start_time = None
        self.auto_send_running = False
        self.auto_send_thread = None

        # 送信モード設定（最後に押されたボタンによる）
        self.last_button_pressed = "manual"  # "manual" or "auto"
        self.manual_speed = 0
        self.manual_is_running = False
        self.manual_is_take = False

        # データ格納用（実際のArduinoデータ形式に合わせる）
        self.latest_data = {
            "motor": {
                "angle": 0.0,
                "speed": 0.0,
                "current": 0.0,
                "temp": 0,
                "torque": 0,
            },
            "control": {
                "target_rpm": 0,
                "current_rpm": 0.0,
                "output_current": 0.0,
                "error": 0.0,
            },
            "accel": {"x": 0.0, "y": 0.0, "z": 0.0},
            "gyro": {"x": 0.0, "y": 0.0, "z": 0.0, "raw_z": 0.0},
            "timestamp": 0,
            "counter": 0,
        }

        # グラフ用データ（最新200ポイント）
        self.accel_history = {
            "x": deque(maxlen=200),
            "y": deque(maxlen=200),
            "z": deque(maxlen=200),
        }
        self.gyro_history = {
            "x": deque(maxlen=200),
            "y": deque(maxlen=200),
            "z": deque(maxlen=200),
            "raw_z": deque(maxlen=200),
        }
        self.motor_history = {"angle": deque(maxlen=200), "speed": deque(maxlen=200)}
        self.command_history = {"speed": deque(maxlen=200)}  # コマンド送信速度の履歴

        # GUI要素のID
        self.text_ids = {}
        self.plot_ids = {}
        self.gui_elements = {}  # GUI要素の参照を保持

        # データ保存フラグ
        self.save_to_db_enabled = False

        # DBマネージャーの初期化
        self.db_manager = ThrowDataManager()

        self.received_data_queue = queue.Queue()

    def start_udp_receiver(self):
        """UDP受信スレッドを開始"""
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.listen_port))
        self.sock.settimeout(1.0)

        # UDP送信用ソケットも作成
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # UDP受信スレッド
        udp_thread = threading.Thread(target=self.udp_receive_loop)
        udp_thread.daemon = True
        udp_thread.start()

        print(f"UDP receiver started on port {self.listen_port}")
        print(f"UDP sender ready to send to {self.send_host}:{self.send_port}")

    def udp_receive_loop(self):
        """UDP受信ループ"""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                message = data.decode("utf-8")

                try:
                    json_data = json.loads(message)
                    self.update_data(json_data)

                except json.JSONDecodeError:
                    print(f"Invalid JSON received: {message[:100]}...")

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"UDP receive error: {e}")

    def update_data(self, data):
        """受信したデータを更新"""
        self.latest_data = data

        # 履歴データに追加
        if "accel" in data:
            self.accel_history["x"].append(data["accel"]["x"])
            self.accel_history["y"].append(data["accel"]["y"])
            self.accel_history["z"].append(data["accel"]["z"])

        if "gyro" in data:
            self.gyro_history["x"].append(data["gyro"]["x"])
            self.gyro_history["y"].append(data["gyro"]["y"])
            self.gyro_history["z"].append(data["gyro"]["z"])
            if "raw_z" in data["gyro"]:
                self.gyro_history["raw_z"].append(data["gyro"]["raw_z"])

        if "motor" in data:
            self.motor_history["angle"].append(data["motor"]["angle"])
            self.motor_history["speed"].append(data["motor"]["speed"])

        # UDP受信時に自動でコマンドを送信
        # self.auto_send_command_on_receive()

        # DB保存処理
        if self.save_to_db_enabled:
            asyncio.run(self.db_manager.save_sensor_data(self.latest_data))

    def auto_send_command_on_receive(self):
        """UDP受信時に自動でコマンドを送信"""
        try:
            if self.last_button_pressed == "auto":
                # Auto Sendモード：サイン波振幅値を送信
                if self.sine_mode_enabled:
                    if self.sine_start_time is None:
                        self.sine_start_time = time.time()
                    speed = self.get_sine_speed()
                else:
                    speed = 0
                is_running = True
                is_take = False
            else:
                # Manualモード：設定値をそのまま送信
                speed = self.manual_speed
                is_running = self.manual_is_running
                is_take = self.manual_is_take

            self.send_command(speed, is_running, is_take)
        except Exception as e:
            print(f"Auto send command error: {e}")

    def send_command(self, speed, is_running, is_take):
        """コマンドをUDP送信"""
        if self.send_sock is None:
            print("Send socket not initialized")
            return

        # RPMからrad/sに変換（1 RPM = π/30 rad/s ≈ 0.10472 rad/s）
        speed_rad_per_sec = speed * 3.14159 / 30.0

        command_data = {
            "angular_velocity": speed_rad_per_sec,
            "isRunning": is_running,
            "isTake": is_take,
        }

        # コマンド速度を履歴に追加（内部的にはRPMのまま）
        self.command_history["speed"].append(speed)

        try:
            message = json.dumps(command_data)
            self.send_sock.sendto(
                message.encode("utf-8"), (self.send_host, self.send_port)
            )
            # print(
            #     f"Sent command: {message} (RPM: {speed} -> rad/s: {speed_rad_per_sec:.3f})"
            # )
        except Exception as e:
            print(f"UDP send error: {e}")

    def get_sine_speed(self):
        """サインモードでの速度計算"""
        if not self.sine_mode_enabled:
            return 0

        if self.sine_start_time is None:
            self.sine_start_time = time.time()

        # 3秒で1周期 (2π rad/3s = 2.094 rad/s)
        elapsed_time = time.time() - self.sine_start_time
        frequency = 1.0 / 3.0  # 3秒で1周期
        angle = 2 * 3.14159 * frequency * elapsed_time

        # サイン波で速度を計算 (-amplitude ~ +amplitude)
        import math

        speed = int(self.sine_amplitude * math.sin(angle))
        return speed

    def start_auto_send(self, callback):
        """自動送信を開始"""
        if not self.auto_send_running:
            self.auto_send_running = True
            self.auto_send_thread = threading.Thread(
                target=self.auto_send_loop, args=(callback,)
            )
            self.auto_send_thread.daemon = True
            self.auto_send_thread.start()
            print("Auto send started")

    def stop_auto_send(self):
        """自動送信を停止"""
        self.auto_send_running = False
        print("Auto send stopped")

    def auto_send_loop(self, callback):
        """自動送信ループ"""
        while self.auto_send_running and self.running:
            if self.sine_mode_enabled:
                callback()
            time.sleep(0.1)  # 100ms間隔

    def update_gui(self):
        """GUI表示を更新"""
        try:
            # 加速度データ更新
            dpg.set_value(
                self.text_ids["accel_x"],
                f"X: {self.latest_data['accel']['x']:.3f} m/s²",
            )
            dpg.set_value(
                self.text_ids["accel_y"],
                f"Y: {self.latest_data['accel']['y']:.3f} m/s²",
            )
            dpg.set_value(
                self.text_ids["accel_z"],
                f"Z: {self.latest_data['accel']['z']:.3f} m/s²",
            )

            # ジャイロデータ更新
            dpg.set_value(
                self.text_ids["gyro_x"], f"X: {self.latest_data['gyro']['x']:.3f} deg/s"
            )
            dpg.set_value(
                self.text_ids["gyro_y"], f"Y: {self.latest_data['gyro']['y']:.3f} deg/s"
            )
            dpg.set_value(
                self.text_ids["gyro_z"], f"Z: {self.latest_data['gyro']['z']:.3f} deg/s"
            )
            if "raw_z" in self.latest_data["gyro"]:
                dpg.set_value(
                    self.text_ids["gyro_raw_z"],
                    f"Raw Z: {self.latest_data['gyro']['raw_z']:.3f} deg/s",
                )

            # モーターデータ更新（実際のArduinoデータ形式に合わせる）
            dpg.set_value(
                self.text_ids["motor_angle"],
                f"Angle: {self.latest_data['motor']['angle']:.3f}°",
            )
            dpg.set_value(
                self.text_ids["motor_speed"],
                f"Speed: {self.latest_data['motor']['speed']} rpm",
            )
            dpg.set_value(
                self.text_ids["motor_temp"],
                f"Temp: {self.latest_data['motor']['temp']}°C",
            )
            # currentフィールドの表示
            current = self.latest_data.get("motor", {}).get("current", 0)
            dpg.set_value(
                self.text_ids["motor_current"],
                f"Current: {current:.3f} A",
            )
            # torqueフィールドの安全な取得
            torque = self.latest_data.get("motor", {}).get("torque", 0)
            dpg.set_value(
                self.text_ids["motor_torque"],
                f"Torque: {torque}",
            )

            # controlデータ更新
            if "control" in self.latest_data:
                dpg.set_value(
                    self.text_ids["control_target_rpm"],
                    f"Target RPM: {self.latest_data['control']['target_rpm']}",
                )
                dpg.set_value(
                    self.text_ids["control_current_rpm"],
                    f"Current RPM: {self.latest_data['control']['current_rpm']}",
                )
                dpg.set_value(
                    self.text_ids["control_output_current"],
                    f"Output Current: {self.latest_data['control']['output_current']:.2f} A",
                )
                dpg.set_value(
                    self.text_ids["control_error"],
                    f"Error: {self.latest_data['control']['error']:.1f}",
                )

            # ステータス更新
            dpg.set_value(
                self.text_ids["counter"], f"Counter: {self.latest_data['counter']}"
            )
            dpg.set_value(
                self.text_ids["timestamp"], f"Time: {self.latest_data['timestamp']} ms"
            )

            # グラフ更新
            if len(self.accel_history["x"]) > 0:
                x_data = list(range(len(self.accel_history["x"])))
                dpg.set_value("accel_plot_x", [x_data, list(self.accel_history["x"])])
                dpg.set_value("accel_plot_y", [x_data, list(self.accel_history["y"])])
                dpg.set_value("accel_plot_z", [x_data, list(self.accel_history["z"])])
                # 加速度グラフの軸を自動調整
                dpg.fit_axis_data("accel_x_axis")
                dpg.fit_axis_data("accel_y_axis")

            if len(self.gyro_history["x"]) > 0:
                x_data = list(range(len(self.gyro_history["x"])))
                dpg.set_value("gyro_plot_x", [x_data, list(self.gyro_history["x"])])
                dpg.set_value("gyro_plot_y", [x_data, list(self.gyro_history["y"])])
                dpg.set_value("gyro_plot_z", [x_data, list(self.gyro_history["z"])])
                if len(self.gyro_history["raw_z"]) > 0:
                    dpg.set_value(
                        "gyro_plot_raw_z", [x_data, list(self.gyro_history["raw_z"])]
                    )
                # ジャイログラフの軸を自動調整
                dpg.fit_axis_data("gyro_x_axis")
                dpg.fit_axis_data("gyro_y_axis")

            if len(self.motor_history["angle"]) > 0:
                x_data = list(range(len(self.motor_history["angle"])))
                dpg.set_value(
                    "motor_plot_angle", [x_data, list(self.motor_history["angle"])]
                )
                dpg.set_value(
                    "motor_plot_speed", [x_data, list(self.motor_history["speed"])]
                )
                # モーターグラフの軸を自動調整
                dpg.fit_axis_data("motor_angle_x_axis")
                dpg.fit_axis_data("motor_angle_y_axis")
                dpg.fit_axis_data("motor_speed_x_axis")
                dpg.fit_axis_data("motor_speed_y_axis")

            # コマンド速度グラフ更新
            if len(self.command_history["speed"]) > 0:
                x_data = list(range(len(self.command_history["speed"])))
                dpg.set_value(
                    "command_plot_speed", [x_data, list(self.command_history["speed"])]
                )

        except Exception as e:
            print(f"GUI update error: {e}")

    def create_gui(self):
        """GUI作成"""
        dpg.create_context()

        # フォント設定（日本語対応）
        with dpg.font_registry():
            default_font = dpg.add_font("c:/windows/fonts/msgothic.ttc", 16)

        # メインウィンドウ（グラフ表示専用）
        with dpg.window(label="Sensor Data Graphs", tag="Primary Window"):
            # 2x2のレイアウト
            with dpg.group(horizontal=True):
                # 左列
                with dpg.group():
                    # 加速度セクション
                    with dpg.collapsing_header(
                        label="Acceleration (m/s²)", default_open=True
                    ):
                        # 加速度グラフ（大きくする）
                        with dpg.plot(label="Acceleration Plot", height=300, width=700):
                            dpg.add_plot_legend()
                            dpg.add_plot_axis(
                                dpg.mvXAxis, label="Time", tag="accel_x_axis"
                            )
                            with dpg.plot_axis(
                                dpg.mvYAxis, label="m/s²", tag="accel_y_axis"
                            ):
                                dpg.add_line_series(
                                    [], [], label="X", tag="accel_plot_x"
                                )
                                dpg.add_line_series(
                                    [], [], label="Y", tag="accel_plot_y"
                                )
                                dpg.add_line_series(
                                    [], [], label="Z", tag="accel_plot_z"
                                )

                    dpg.add_spacer(height=20)

                    # ジャイロセクション
                    with dpg.collapsing_header(
                        label="Gyroscope (deg/s)", default_open=True
                    ):
                        # ジャイログラフ（大きくする）
                        with dpg.plot(label="Gyroscope Plot", height=300, width=700):
                            dpg.add_plot_legend()
                            dpg.add_plot_axis(
                                dpg.mvXAxis, label="Time", tag="gyro_x_axis"
                            )
                            with dpg.plot_axis(
                                dpg.mvYAxis, label="deg/s", tag="gyro_y_axis"
                            ):
                                dpg.add_line_series(
                                    [], [], label="X", tag="gyro_plot_x"
                                )
                                dpg.add_line_series(
                                    [], [], label="Y", tag="gyro_plot_y"
                                )
                                dpg.add_line_series(
                                    [], [], label="Z", tag="gyro_plot_z"
                                )
                                dpg.add_line_series(
                                    [], [], label="Raw Z", tag="gyro_plot_raw_z"
                                )

                dpg.add_spacer(width=30)

                # 右列
                with dpg.group():
                    # モーター角度セクション
                    with dpg.collapsing_header(
                        label="Motor Angle (deg)", default_open=True
                    ):
                        # 角度グラフ（大きくする）
                        with dpg.plot(label="Motor Angle Plot", height=300, width=700):
                            dpg.add_plot_legend()
                            dpg.add_plot_axis(
                                dpg.mvXAxis, label="Time", tag="motor_angle_x_axis"
                            )
                            with dpg.plot_axis(
                                dpg.mvYAxis, label="deg", tag="motor_angle_y_axis"
                            ):
                                dpg.add_line_series(
                                    [], [], label="Angle", tag="motor_plot_angle"
                                )

                    dpg.add_spacer(height=20)

                    # モーター回転数セクション
                    with dpg.collapsing_header(
                        label="Motor Speed (RPM)", default_open=True
                    ):
                        # 速度グラフ（大きくする）
                        with dpg.plot(label="Motor Speed Plot", height=300, width=700):
                            dpg.add_plot_legend()
                            dpg.add_plot_axis(
                                dpg.mvXAxis, label="Time", tag="motor_speed_x_axis"
                            )
                            with dpg.plot_axis(
                                dpg.mvYAxis, label="RPM", tag="motor_speed_y_axis"
                            ):
                                dpg.add_line_series(
                                    [], [], label="Motor Speed", tag="motor_plot_speed"
                                )
                                dpg.add_line_series(
                                    [],
                                    [],
                                    label="Command Speed",
                                    tag="command_plot_speed",
                                )

        # データ表示ウィンドウ（数値専用）
        with dpg.window(
            label="Sensor Data Values",
            tag="Data Window",
            width=400,
            height=600,
            pos=[1450, 50],
        ):
            # ステータス表示
            with dpg.group():
                self.text_ids["counter"] = dpg.add_text("Counter: 0")
                self.text_ids["timestamp"] = dpg.add_text("Time: 0 ms")

            dpg.add_separator()

            # 加速度データ
            with dpg.collapsing_header(label="Acceleration", default_open=True):
                self.text_ids["accel_x"] = dpg.add_text("X: 0.000 m/s²")
                self.text_ids["accel_y"] = dpg.add_text("Y: 0.000 m/s²")
                self.text_ids["accel_z"] = dpg.add_text("Z: 0.000 m/s²")

            dpg.add_separator()

            # ジャイロデータ
            with dpg.collapsing_header(label="Gyroscope", default_open=True):
                self.text_ids["gyro_x"] = dpg.add_text("X: 0.000 deg/s")
                self.text_ids["gyro_y"] = dpg.add_text("Y: 0.000 deg/s")
                self.text_ids["gyro_z"] = dpg.add_text("Z: 0.000 deg/s")
                self.text_ids["gyro_raw_z"] = dpg.add_text("Raw Z: 0.000 deg/s")

            dpg.add_separator()

            # コントロールデータ
            with dpg.collapsing_header(label="Control", default_open=True):
                self.text_ids["control_target_rpm"] = dpg.add_text("Target RPM: 0")
                self.text_ids["control_current_rpm"] = dpg.add_text("Current RPM: 0")
                self.text_ids["control_output_current"] = dpg.add_text(
                    "Output Current: 0.00 A"
                )
                self.text_ids["control_error"] = dpg.add_text("Error: 0.0")

            dpg.add_separator()

            # コマンド送信セクション
            with dpg.collapsing_header(label="Send Command", default_open=True):
                # Manual Mode設定
                with dpg.collapsing_header(
                    label="Manual Mode Settings", default_open=True
                ):
                    dpg.add_text("Manual Speed:")
                    speed_input = dpg.add_input_int(
                        label="##speed",
                        default_value=0,
                        min_value=-1000,
                        max_value=1000,
                    )

                    # チェックボックス
                    is_running_checkbox = dpg.add_checkbox(
                        label="isRunning", default_value=False
                    )
                    is_take_checkbox = dpg.add_checkbox(
                        label="isTake", default_value=False
                    )

                    # GUI要素の参照を保存
                    self.gui_elements["speed_input"] = speed_input
                    self.gui_elements["is_running_checkbox"] = is_running_checkbox
                    self.gui_elements["is_take_checkbox"] = is_take_checkbox

                    # Manual送信ボタン
                    def manual_send_callback():
                        self.last_button_pressed = "manual"
                        self.manual_speed = dpg.get_value(speed_input)
                        self.manual_is_running = dpg.get_value(is_running_checkbox)
                        self.manual_is_take = dpg.get_value(is_take_checkbox)
                        self.send_command(
                            self.manual_speed,
                            self.manual_is_running,
                            self.manual_is_take,
                        )
                        print(f"Manual mode activated - Speed: {self.manual_speed}")

                    dpg.add_button(
                        label="Send Manual Command", callback=manual_send_callback
                    )

                dpg.add_separator()

                # Auto Send Mode設定
                with dpg.collapsing_header(
                    label="Auto Send Mode Settings", default_open=True
                ):
                    dpg.add_text("Sine Mode:")
                    sine_mode_checkbox = dpg.add_checkbox(
                        label="Enable Sine Mode", default_value=False
                    )

                    dpg.add_text("Sine Amplitude:")
                    sine_amplitude_input = dpg.add_input_int(
                        label="##sine_amplitude",
                        default_value=100,
                        min_value=0,
                        max_value=1000,
                    )

                    # 現在の速度表示
                    current_speed_text = dpg.add_text("Current Speed: 0")

                    # Auto Send Mode設定更新関数
                    def activate_auto_mode():
                        self.last_button_pressed = "auto"

                        # Auto Send Mode設定を更新
                        self.sine_mode_enabled = dpg.get_value(sine_mode_checkbox)
                        self.sine_amplitude = dpg.get_value(sine_amplitude_input)

                        if self.sine_mode_enabled:
                            if self.sine_start_time is None:
                                self.sine_start_time = time.time()
                            speed = self.get_sine_speed()
                            dpg.set_value(current_speed_text, f"Current Speed: {speed}")

                        print(
                            f"Auto mode activated - Sine enabled: {self.sine_mode_enabled}, Amplitude: {self.sine_amplitude}"
                        )

                    # Auto Send Mode有効化ボタン
                    dpg.add_button(
                        label="Activate Auto Send Mode", callback=activate_auto_mode
                    )

            dpg.add_separator()

            # モーターデータ
            with dpg.collapsing_header(label="Motor", default_open=True):
                self.text_ids["motor_angle"] = dpg.add_text("Angle: 0°")
                self.text_ids["motor_speed"] = dpg.add_text("Speed: 0 rpm")
                self.text_ids["motor_current"] = dpg.add_text("Current: 0.000 A")
                self.text_ids["motor_temp"] = dpg.add_text("Temp: 0°C")
                self.text_ids["motor_torque"] = dpg.add_text("Torque: 0")

        with dpg.window(
            label="Data Save Control",
            tag="SaveControlWindow",
            width=400,
            height=100,
            pos=[1450, 700],
        ):

            def save_checkbox_callback(sender, app_data):
                self.save_to_db_enabled = app_data

            dpg.add_checkbox(
                label="Save Received Data to DB",
                default_value=False,
                callback=save_checkbox_callback,
            )

        dpg.bind_font(default_font)

        dpg.create_viewport(title="M5Stack Sensor Data Monitor", width=1900, height=900)
        dpg.set_viewport_vsync(True)  # VSync有効化
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("Primary Window", True)

    def run(self):
        """アプリケーション実行"""
        self.start_udp_receiver()
        self.create_gui()

        # メインループ（VSync使用時は自動的に画面更新レートに合わせられる）
        while dpg.is_dearpygui_running():
            self.update_gui()
            dpg.render_dearpygui_frame()
            # VSync有効時はsleepを短くするか削除可能
            # time.sleep(0.001)  # 最小限のCPU負荷軽減

        # クリーンアップ
        self.running = False
        self.auto_send_running = False
        if self.sock:
            self.sock.close()
        if self.send_sock:
            self.send_sock.close()
        dpg.destroy_context()


def main():
    print("Sensor Data Monitor - Starting...")

    monitor = SensorDataGUI()

    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\nMonitor stopping...")
        monitor.running = False
        print("Monitor stopped.")


if __name__ == "__main__":
    main()
