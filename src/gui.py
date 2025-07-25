import socket
import json
import threading
import time
import dearpygui.dearpygui as dpg
from collections import deque


class SensorDataGUI:
    def __init__(self, listen_port=8888):
        self.listen_port = listen_port
        self.running = False
        self.sock = None

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

        # GUI要素のID
        self.text_ids = {}
        self.plot_ids = {}

    def start_udp_receiver(self):
        """UDP受信スレッドを開始"""
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.listen_port))
        self.sock.settimeout(1.0)

        # UDP受信スレッド
        udp_thread = threading.Thread(target=self.udp_receive_loop)
        udp_thread.daemon = True
        udp_thread.start()

        print(f"UDP receiver started on port {self.listen_port}")

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
                                    [], [], label="Speed", tag="motor_plot_speed"
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

            # モーターデータ
            with dpg.collapsing_header(label="Motor", default_open=True):
                self.text_ids["motor_angle"] = dpg.add_text("Angle: 0°")
                self.text_ids["motor_speed"] = dpg.add_text("Speed: 0 rpm")
                self.text_ids["motor_current"] = dpg.add_text("Current: 0.000 A")
                self.text_ids["motor_temp"] = dpg.add_text("Temp: 0°C")
                self.text_ids["motor_torque"] = dpg.add_text("Torque: 0")

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
        if self.sock:
            self.sock.close()
        dpg.destroy_context()


def main():
    print("Sensor Data Monitor - Starting...")

    monitor = SensorDataGUI(listen_port=8888)

    try:
        monitor.run()
    except KeyboardInterrupt:
        print("\nMonitor stopping...")
        monitor.running = False
        print("Monitor stopped.")


if __name__ == "__main__":
    main()
