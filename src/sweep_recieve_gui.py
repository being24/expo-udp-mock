import asyncio
import json
import socket
import threading
from collections import deque

import dearpygui.dearpygui as dpg

from sweep_data_manager import SweepDataManager


class SweepReceiveGUI:
    def __init__(self, listen_port=8800):
        self.listen_port = listen_port
        self.running = False
        self.sock = None
        self.latest_data = {
            "ax": 0.0,
            "ay": 0.0,
            "az": 0.0,
            "pressure": 0,
            "counter": 0,
        }
        self.ax_history = deque(maxlen=200)
        self.ay_history = deque(maxlen=200)
        self.az_history = deque(maxlen=200)
        self.text_ids = {}
        self.save_to_db_enabled = False
        self.db_manager = SweepDataManager()
        asyncio.run(self.db_manager.create_table())
        self.counter = 0

    def start_udp_receiver(self):
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.listen_port))
        self.sock.settimeout(1.0)
        udp_thread = threading.Thread(target=self.udp_receive_loop)
        udp_thread.daemon = True
        udp_thread.start()
        print(f"UDP receiver started on port {self.listen_port}")

    def udp_receive_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                message = data.decode("utf-8")
                try:
                    json_data = json.loads(message)
                    self.counter += 1
                    json_data["counter"] = self.counter
                    self.update_data(json_data)

                except json.JSONDecodeError:
                    print(f"Invalid JSON received: {message[:100]}...")
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"UDP receive error: {e}")

    def update_data(self, data):
        self.latest_data = data
        self.ax_history.append(data.get("ax", 0.0))
        self.ay_history.append(data.get("ay", 0.0))
        self.az_history.append(data.get("az", 0.0))

        if self.save_to_db_enabled:
            asyncio.run(self.db_manager.save(self.latest_data))

    def update_gui(self):
        try:
            dpg.set_value(self.text_ids["ax"], f"ax: {self.latest_data['ax']:.4f}")
            dpg.set_value(self.text_ids["ay"], f"ay: {self.latest_data['ay']:.4f}")
            dpg.set_value(self.text_ids["az"], f"az: {self.latest_data['az']:.4f}")
            dpg.set_value(
                self.text_ids["pressure"], f"pressure: {self.latest_data['pressure']}"
            )
            dpg.set_value(
                self.text_ids["counter"], f"counter: {self.latest_data['counter']}"
            )
            if len(self.ax_history) > 0:
                x_data = list(range(len(self.ax_history)))
                dpg.set_value("ax_plot", [x_data, list(self.ax_history)])
                dpg.set_value("ay_plot", [x_data, list(self.ay_history)])
                dpg.set_value("az_plot", [x_data, list(self.az_history)])
                dpg.fit_axis_data("ax_axis")
                dpg.fit_axis_data("ay_axis")
        except Exception as e:
            print(f"GUI update error: {e}")

    def create_gui(self):
        dpg.create_context()
        with dpg.font_registry():
            # data/Noto_Sans_JP/NotoSansJP-VariableFont_wght.ttf
            default_font = dpg.add_font(
                "data/Noto_Sans_JP/static/NotoSansJP-Bold.ttf", 24
            )

        with dpg.window(label="Sweep Sensor Data", tag="Primary Window"):
            with dpg.group():
                self.text_ids["ax"] = dpg.add_text("ax: 0.0000")
                self.text_ids["ay"] = dpg.add_text("ay: 0.0000")
                self.text_ids["az"] = dpg.add_text("az: 0.0000")
                self.text_ids["pressure"] = dpg.add_text("pressure: 0")
                self.text_ids["counter"] = dpg.add_text("counter: 0")
            dpg.add_spacer(height=20)
            with dpg.plot(label="Acceleration Plot", height=300, width=700):
                dpg.add_plot_legend()
                dpg.add_plot_axis(dpg.mvXAxis, label="Time", tag="ax_axis")
                with dpg.plot_axis(dpg.mvYAxis, label="m/s²", tag="ay_axis"):
                    dpg.add_line_series([], [], label="ax", tag="ax_plot")
                    dpg.add_line_series([], [], label="ay", tag="ay_plot")
                    dpg.add_line_series([], [], label="az", tag="az_plot")
        with dpg.window(
            label="Data Save Control",
            tag="SaveControlWindow",
            width=400,
            height=100,
            pos=[300, 30],
        ):

            def save_checkbox_callback(sender, app_data):
                self.save_to_db_enabled = app_data

            dpg.add_checkbox(
                label="Save Received Data to DB",
                default_value=False,
                callback=save_checkbox_callback,
            )
        dpg.bind_font(default_font)
        dpg.create_viewport(title="Sweep Sensor Data Monitor", width=900, height=500)
        dpg.set_viewport_vsync(True)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("Primary Window", True)

    def run(self):
        self.start_udp_receiver()
        self.create_gui()
        while dpg.is_dearpygui_running():
            self.update_gui()
            dpg.render_dearpygui_frame()
        self.running = False
        if self.sock:
            self.sock.close()
        dpg.destroy_context()


if __name__ == "__main__":
    print("Sweep Sensor Data Monitor - Starting...")
    gui = SweepReceiveGUI()
    try:
        gui.run()
    except KeyboardInterrupt:
        print("Monitor stopping...")
        gui.running = False
        print("Monitor stopped.")
