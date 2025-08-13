import asyncio
import json
import socket
import threading
import time
import random
from typing import List

import dearpygui.dearpygui as dpg

from peak_data_manager import PeakDataManager, PeakDataModel


class UDPSenderGUI:
    def __init__(self):
        self.peak_data_manager = PeakDataManager()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Network settings
        self.target_ip = "127.0.0.1"
        self.target_port = 9001
        self.send_interval = 0.05  # 50ms (fallback for random data)

        # Transmission state
        self.is_sending = False
        self.send_thread = None
        self.current_data_list: List[PeakDataModel] = []
        self.throw_ids: List[int] = []
        self.current_data_index = 0
        self.is_replaying = False
        self.use_real_timing = True

        # GUI element tags
        self.status_text = "status_text"
        self.data_count_text = "data_count_text"
        self.replay_progress_text = "replay_progress_text"
        self.throw_id_combo = "throw_id_combo"
        self.throw_ids_count_text = "throw_ids_count_text"

    def generate_random_data(self) -> dict:
        """Generate random sensor data (mostly zeros)"""
        current_time = int(time.time() * 1000)
        base_counter = int(current_time / 100) % 10000

        return {
            "timestamp": current_time,
            "counter": base_counter,
            "motor": {
                "angle": random.uniform(-0.1, 0.1),
                "speed": random.uniform(-0.1, 0.1),
                "current": random.uniform(-0.01, 0.01),
                "temp": random.randint(0, 1),
                "torque": random.randint(-1, 1),
            },
            "control": {
                "target_rpm": 0,
                "current_rpm": random.uniform(-0.1, 0.1),
                "output_current": random.uniform(-0.01, 0.01),
                "error": random.uniform(-0.01, 0.01),
            },
            "accel": {
                "x": random.uniform(-0.01, 0.01),
                "y": random.uniform(-0.01, 0.01),
                "z": random.uniform(-0.99, -1.01),  # Around 1G for gravity
            },
            "gyro": {
                "x": random.uniform(-0.01, 0.01),
                "y": random.uniform(-0.01, 0.01),
                "z": random.uniform(-0.01, 0.01),
                "raw_z": random.uniform(-0.01, 0.01),
            },
        }

    def peak_model_to_json(self, model: PeakDataModel) -> dict:
        """Convert PeakDataModel to JSON format"""
        return {
            "timestamp": model.timestamp,
            "counter": model.counter,
            "throw_id": model.throw_id,
            "motor": {
                "angle": model.motor_angle,
                "speed": model.motor_speed,
                "current": model.motor_current,
                "temp": model.motor_temp,
                "torque": model.motor_torque,
            },
            "control": {
                "target_rpm": model.control_target_rpm,
                "current_rpm": model.control_current_rpm,
                "output_current": model.control_output_current,
                "error": model.control_error,
            },
            "accel": {"x": model.accel_x, "y": model.accel_y, "z": model.accel_z},
            "gyro": {
                "x": model.gyro_x,
                "y": model.gyro_y,
                "z": model.gyro_z,
                "raw_z": model.gyro_raw_z,
            },
        }

    def send_data_loop(self):
        """Data transmission loop (runs in separate thread)"""
        last_timestamp = None

        while self.is_sending:
            try:
                current_sleep_time = self.send_interval

                if self.is_replaying and self.current_data_list:
                    # Peak data replay with real timing
                    if self.current_data_index < len(self.current_data_list):
                        data = self.current_data_list[self.current_data_index]
                        json_data = self.peak_model_to_json(data)

                        # Calculate real timing interval
                        if self.use_real_timing and last_timestamp is not None:
                            time_diff = data.timestamp - last_timestamp
                            if time_diff > 0:
                                current_sleep_time = time_diff / 1000.0

                        last_timestamp = data.timestamp
                        self.current_data_index += 1

                        # Progress update
                        progress = (
                            f"{self.current_data_index}/{len(self.current_data_list)}"
                        )
                        dpg.set_value(
                            self.replay_progress_text, f"Replay Progress: {progress}"
                        )
                    else:
                        # Replay finished
                        self.is_replaying = False
                        self.current_data_index = 0
                        last_timestamp = None
                        dpg.set_value(self.replay_progress_text, "Replay Complete")
                        json_data = self.generate_random_data()
                        current_sleep_time = self.send_interval
                else:
                    # Random data
                    json_data = self.generate_random_data()
                    last_timestamp = None
                    current_sleep_time = self.send_interval

                # UDP transmission
                message = json.dumps(json_data).encode("utf-8")
                self.socket.sendto(message, (self.target_ip, self.target_port))

                # Status update
                status = (
                    "Replaying Peak Data"
                    if self.is_replaying
                    else "Sending Random Data"
                )
                dpg.set_value(self.status_text, f"Status: {status}")

            except Exception as e:
                dpg.set_value(self.status_text, f"Send Error: {str(e)}")
                current_sleep_time = self.send_interval

            time.sleep(current_sleep_time)

    def start_sending(self):
        """Start transmission"""
        if not self.is_sending:
            self.is_sending = True
            self.send_thread = threading.Thread(target=self.send_data_loop, daemon=True)
            self.send_thread.start()
            dpg.set_value(self.status_text, "Status: Started")

    def stop_sending(self):
        """Stop transmission"""
        self.is_sending = False
        if self.send_thread:
            self.send_thread.join(timeout=1.0)
        dpg.set_value(self.status_text, "Status: Stopped")
        dpg.set_value(self.replay_progress_text, "")

    def start_replay(self, sender, app_data):
        """Start peak data replay"""
        if self.current_data_list:
            self.is_replaying = True
            self.current_data_index = 0
            dpg.set_value(self.replay_progress_text, "Replay Started")

            if not self.is_sending:
                self.start_sending()

    async def load_throw_ids(self):
        """Load available throw IDs from database"""
        try:
            await self.peak_data_manager.create_table()
            throw_ids = await self.peak_data_manager.get_throw_ids()

            if throw_ids:
                self.throw_ids = throw_ids
                dpg.set_value(
                    self.throw_ids_count_text, f"Available Throw IDs: {len(throw_ids)}"
                )

                # Update combo box with throw IDs
                self.update_throw_id_combo()
                return True
            else:
                dpg.set_value(self.throw_ids_count_text, "No throw IDs found")
                return False
        except Exception as e:
            dpg.set_value(self.throw_ids_count_text, f"Load Error: {str(e)}")
            return False

    def update_throw_id_combo(self):
        """Update combo box with available throw IDs"""
        if not self.throw_ids:
            dpg.configure_item(self.throw_id_combo, items=["No data available"])
            return

        # Create display items for throw IDs
        items = []
        for throw_id in self.throw_ids:
            items.append(f"Throw ID: {throw_id}")

        dpg.configure_item(self.throw_id_combo, items=items)
        if items:
            dpg.set_value(self.throw_id_combo, items[0])
            # Auto-load first throw ID data
            self.select_throw_id(None, None)

    async def load_throw_data(self, throw_id: int):
        """Load data for specific throw ID"""
        try:
            data_list = await self.peak_data_manager.get_data_by_throw_id(throw_id)
            if data_list:
                # Sort by timestamp to ensure correct order
                self.current_data_list = sorted(data_list, key=lambda x: x.timestamp)
                dpg.set_value(
                    self.data_count_text,
                    f"Loaded Data Count: {len(self.current_data_list)}",
                )
                return True
            else:
                self.current_data_list = []
                dpg.set_value(self.data_count_text, "No data found for this throw ID")
                return False
        except Exception as e:
            dpg.set_value(self.data_count_text, f"Load Error: {str(e)}")
            return False

    def select_throw_id(self, sender, app_data):
        """Select throw ID from combo box"""
        selected = dpg.get_value(self.throw_id_combo)
        if not selected or selected == "No data available":
            return

        try:
            # Extract throw ID from selection (e.g., "Throw ID: 15" -> 15)
            throw_id = int(selected.split(": ")[1])

            # Load data for selected throw ID
            def run_async():
                asyncio.run(self.load_throw_data(throw_id))

            threading.Thread(target=run_async, daemon=True).start()
        except (ValueError, IndexError):
            dpg.set_value(self.data_count_text, "Invalid throw ID selection")

    def load_throw_ids_callback(self, sender, app_data):
        """Load throw IDs button callback"""

        def run_async():
            asyncio.run(self.load_throw_ids())

        threading.Thread(target=run_async, daemon=True).start()

    def update_network_settings(self, sender, app_data):
        """Update network settings"""
        self.target_ip = dpg.get_value("ip_input")
        self.target_port = dpg.get_value("port_input")
        self.send_interval = dpg.get_value("interval_input") / 1000.0

    def toggle_timing_mode(self, sender, app_data):
        """Toggle between real timing and fixed interval"""
        self.use_real_timing = dpg.get_value("timing_checkbox")

    def create_gui(self):
        """Create GUI"""
        dpg.create_context()

        with dpg.window(label="UDP Peak Data Sender", width=700, height=600):
            # Network settings
            with dpg.group(horizontal=True):
                dpg.add_text("Target IP:")
                dpg.add_input_text(
                    default_value=self.target_ip, tag="ip_input", width=140
                )
                dpg.add_text("Port:")
                dpg.add_input_int(
                    default_value=self.target_port, tag="port_input", width=120
                )
                dpg.add_button(
                    label="Update Settings", callback=self.update_network_settings
                )

            dpg.add_separator()

            # Timing settings
            with dpg.group(horizontal=True):
                dpg.add_text("Fallback Interval (ms):")
                dpg.add_input_int(
                    default_value=int(self.send_interval * 1000),
                    tag="interval_input",
                    width=100,
                    min_value=10,
                    max_value=10000,
                )
                dpg.add_button(label="Update", callback=self.update_network_settings)

            dpg.add_checkbox(
                label="Use Real Timestamp Intervals",
                tag="timing_checkbox",
                default_value=self.use_real_timing,
                callback=self.toggle_timing_mode,
            )

            dpg.add_separator()

            # Database operations
            dpg.add_text("Peak Data Operations:", color=[255, 255, 0])

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Load Throw IDs", callback=self.load_throw_ids_callback
                )
                dpg.add_text("", tag=self.throw_ids_count_text)

            dpg.add_separator()

            # Throw ID selection
            dpg.add_text("Select Throw ID:")
            dpg.add_combo(
                label="Throw ID",
                items=["Load throw IDs first"],
                tag=self.throw_id_combo,
                callback=self.select_throw_id,
                width=300,
            )

            dpg.add_text("Loaded Data Count: 0", tag=self.data_count_text)

            dpg.add_separator()

            # Transmission control
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Start Sending", callback=lambda: self.start_sending()
                )
                dpg.add_button(
                    label="Stop Sending", callback=lambda: self.stop_sending()
                )
                dpg.add_button(label="Replay Peak Data", callback=self.start_replay)

            dpg.add_separator()

            # Status display
            dpg.add_text("Status: Stopped", tag=self.status_text)
            dpg.add_text("", tag=self.replay_progress_text)

            dpg.add_separator()

            # Instructions
            dpg.add_text("How to use:", color=[0, 255, 255])
            dpg.add_text("1. Set target IP and port if needed")
            dpg.add_text("2. Click 'Load Throw IDs' to get available throw IDs")
            dpg.add_text("3. Select a throw ID from dropdown")
            dpg.add_text("4. Start sending random data or replay peak data")
            dpg.add_text("5. Real timing uses actual timestamp intervals from DB")

        dpg.create_viewport(title="UDP Peak Data Sender", width=750, height=650)
        dpg.setup_dearpygui()
        dpg.show_viewport()

    def run(self):
        """Run application"""
        try:
            self.create_gui()

            # Auto-load throw IDs on startup
            def auto_load():
                time.sleep(0.5)  # Wait for GUI to be ready
                asyncio.run(self.load_throw_ids())

            threading.Thread(target=auto_load, daemon=True).start()

            dpg.start_dearpygui()
        finally:
            self.stop_sending()
            self.socket.close()
            dpg.destroy_context()


if __name__ == "__main__":
    app = UDPSenderGUI()
    app.run()
