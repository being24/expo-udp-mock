import socket
import json
import threading
import pathlib
from datetime import datetime
import dearpygui.dearpygui as dpg


class UDPReceiverGUI:
    def __init__(self):
        self.socket = None
        self.listen_ip = "127.0.0.1"
        self.listen_port = 12345
        self.is_listening = False
        self.receive_thread = None
        self.received_count = 0

        # GUI要素のタグ
        self.status_text = "status_text"
        self.count_text = "count_text"
        self.data_display = "data_display"

    def start_listening(self):
        """受信開始"""
        if not self.is_listening:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.socket.bind((self.listen_ip, self.listen_port))
                self.socket.settimeout(1.0)  # タイムアウト設定

                self.is_listening = True
                self.receive_thread = threading.Thread(
                    target=self.receive_loop, daemon=True
                )
                self.receive_thread.start()

                dpg.set_value(
                    self.status_text,
                    f"受信状態: {self.listen_ip}:{self.listen_port}で受信中",
                )
            except Exception as e:
                dpg.set_value(self.status_text, f"受信エラー: {str(e)}")

    def stop_listening(self):
        """受信停止"""
        self.is_listening = False
        if self.socket:
            self.socket.close()
            self.socket = None
        if self.receive_thread:
            self.receive_thread.join(timeout=2.0)
        dpg.set_value(self.status_text, "受信状態: 停止")

    def receive_loop(self):
        """データ受信ループ"""
        while self.is_listening:
            try:
                data, addr = self.socket.recvfrom(4096)
                message = data.decode("utf-8")
                json_data = json.loads(message)

                self.received_count += 1
                dpg.set_value(self.count_text, f"受信回数: {self.received_count}")

                # データ表示を更新
                current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                display_text = f"[{current_time}] 送信元: {addr}\n"
                display_text += f"タイムスタンプ: {json_data.get('timestamp')}\n"
                display_text += f"カウンター: {json_data.get('counter')}\n"

                # モーターデータ
                motor = json_data.get("motor", {})
                display_text += f"モーター角度: {motor.get('angle', 'N/A'):.2f}°\n"
                display_text += f"モーター速度: {motor.get('speed', 'N/A'):.1f} RPM\n"
                display_text += f"モーター電流: {motor.get('current', 'N/A'):.2f} A\n"

                # 加速度データ
                accel = json_data.get("accel", {})
                display_text += f"加速度 X,Y,Z: {accel.get('x', 'N/A'):.3f}, {accel.get('y', 'N/A'):.3f}, {accel.get('z', 'N/A'):.3f} G\n"

                # ジャイロデータ
                gyro = json_data.get("gyro", {})
                display_text += f"ジャイロ X,Y,Z: {gyro.get('x', 'N/A'):.3f}, {gyro.get('y', 'N/A'):.3f}, {gyro.get('z', 'N/A'):.3f} deg/s\n"

                display_text += "-" * 50 + "\n"

                # 最新のデータを先頭に表示（最大1000行まで）
                current_text = dpg.get_value(self.data_display)
                lines = current_text.split("\n")
                new_lines = display_text.split("\n") + lines
                if len(new_lines) > 1000:
                    new_lines = new_lines[:1000]

                dpg.set_value(self.data_display, "\n".join(new_lines))

            except socket.timeout:
                continue
            except json.JSONDecodeError as e:
                dpg.set_value(self.status_text, f"JSONデコードエラー: {str(e)}")
            except Exception as e:
                if self.is_listening:  # エラーが予期しないものの場合のみ表示
                    dpg.set_value(self.status_text, f"受信エラー: {str(e)}")
                break

    def update_network_settings(self, sender, app_data):
        """ネットワーク設定更新"""
        self.listen_ip = dpg.get_value("listen_ip_input")
        self.listen_port = dpg.get_value("listen_port_input")

    def clear_display(self, sender, app_data):
        """表示をクリア"""
        dpg.set_value(self.data_display, "")
        self.received_count = 0
        dpg.set_value(self.count_text, "受信回数: 0")

    def create_gui(self):
        """GUI作成"""
        dpg.create_context()

        # 日本語フォントの設定
        font_path = (
            pathlib.Path(__file__).parent.parent
            / "data"
            / "Noto_Sans_JP"
            / "static"
            / "NotoSansJP-Regular.ttf"
        )

        with dpg.font_registry():
            if font_path.exists():
                default_font = dpg.add_font(str(font_path), 18)
            else:
                print(f"フォントファイルが見つかりません: {font_path}")
                # フォールバック: システムのデフォルトフォント
                default_font = dpg.add_font("c:/windows/fonts/msgothic.ttc", 18)

        dpg.bind_font(default_font)

        with dpg.window(label="UDP Sensor Data Receiver", width=800, height=600):
            # ネットワーク設定
            with dpg.group(horizontal=True):
                dpg.add_text("受信IP:")
                dpg.add_input_text(
                    default_value=self.listen_ip, tag="listen_ip_input", width=120
                )
                dpg.add_text("ポート:")
                dpg.add_input_int(
                    default_value=self.listen_port, tag="listen_port_input", width=80
                )
                dpg.add_button(label="設定更新", callback=self.update_network_settings)

            dpg.add_separator()

            # 受信制御
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="受信開始", callback=lambda: self.start_listening()
                )
                dpg.add_button(label="受信停止", callback=lambda: self.stop_listening())
                dpg.add_button(label="表示クリア", callback=self.clear_display)

            dpg.add_separator()

            # ステータス表示
            dpg.add_text("受信状態: 停止", tag=self.status_text)
            dpg.add_text("受信回数: 0", tag=self.count_text)

            dpg.add_separator()

            # データ表示
            dpg.add_text("受信データ:")
            dpg.add_input_text(
                multiline=True,
                readonly=True,
                default_value="",
                tag=self.data_display,
                width=780,
                height=400,
            )

        dpg.create_viewport(title="UDP Sensor Data Receiver", width=820, height=650)
        dpg.setup_dearpygui()
        dpg.show_viewport()

    def run(self):
        """アプリケーション実行"""
        try:
            self.create_gui()
            dpg.start_dearpygui()
        finally:
            self.stop_listening()
            dpg.destroy_context()


if __name__ == "__main__":
    app = UDPReceiverGUI()
    app.run()
