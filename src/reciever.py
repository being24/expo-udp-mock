import socket
import json
from pprint import PrettyPrinter


class UnityMock:
    def __init__(self, listen_port=8888, target_host="127.0.0.1", target_port=8887):
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.running = False
        self.sock = None
        self.receive_count = 0

        # PrettyPrinterの設定
        self.pp = PrettyPrinter(
            indent=2,  # インデント幅
            width=80,  # 行の最大幅
            depth=None,  # ネストの最大深度（Noneで無制限）
            compact=False,  # コンパクト表示を無効
        )

    def start(self):
        """Unity/PCモックを開始"""
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.listen_port))
        self.sock.settimeout(1.0)

        print("Unity Mock started")
        print(f"Listening on port {self.listen_port}")
        print("Waiting for data...")

        # データ受信ループ
        self.receive_data()

    def receive_data(self):
        """データ受信"""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                message = data.decode("utf-8")

                self.receive_count += 1
                print(f"[#{self.receive_count}] Received from {addr}")

                # JSONとしてパースしてきれいに表示
                try:
                    json_data = json.loads(message)
                    print("Data:")
                    self.pp.pprint(json_data)
                except json.JSONDecodeError:
                    # JSONでない場合は生のテキストを表示
                    print(f"Raw data: {message}")
                print("-" * 60)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[Unity] Receive error: {e}")

    def stop(self):
        """停止"""
        self.running = False
        if self.sock:
            self.sock.close()


def main():
    print("Unity/PC UDP Mock - Starting...")

    unity = UnityMock()

    try:
        unity.start()

    except KeyboardInterrupt:
        print("\n[Unity] Stopping...")
        unity.stop()
        print("[Unity] Stopped.")


if __name__ == "__main__":
    main()
