import asyncio
import pathlib
import sys
from collections import deque
from typing import List

import matplotlib.pyplot as plt
import numpy as np

# パスを追加してデータマネージャをimport
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))
from throw_data_manager import SensorDataModel, ThrowDataManager


def lowpass_filter(data, alpha=0.5):
    y = [data[0]]
    for x in data[1:]:
        y.append(alpha * x + (1 - alpha) * y[-1])
    return y


# 変換とトリム
def convert_and_trim(raw_vel: float) -> float:
    TIMES = 2.5
    double_vel = raw_vel * TIMES
    # もし、raw_velを2倍した値が2.2を下回るならば、2,2にトリム
    if double_vel < 2.2:
        return 2.2
    # raw_velを2倍した値が4.0を上回るならば、4.0にトリム
    elif double_vel > 4.0:
        return 4.0

    # それ以外はそのまま2倍して返す
    return double_vel


def main():
    # ThrowDataManagerのインスタンス化
    manager = ThrowDataManager()

    # グラフ保存パス
    graph_save_path = pathlib.Path(__file__).resolve().parents[2] / "graphs"
    if not graph_save_path.exists():
        graph_save_path.mkdir(parents=True)

    # sweep_dataテーブルの全データを取得
    all_data: List[SensorDataModel] = asyncio.run(manager.get_all_data())

    # queueを使って、10データ分を集めます
    data_queue = deque(maxlen=10)

    over_flag = False
    counter = 0
    G = 9.81  # 重力加速度 [m/s^2]

    created_at_list = []

    # そのデータを全部回す(実際は順番に入ってくるデータ)
    for data in all_data:
        # キューに追加して
        data_queue.append(data)

        # data.accel_xが0.8を超えたら、data.accel_xが負になるまでデータをまって
        if data.accel_x > 0.8:
            over_flag = True
            counter = 0

        # キューの数を超えてデータを探索しないように、ループ回数をカウントする
        if over_flag:
            counter += 1

        # accel_xが0.8を超えてから、最後にaccel_xが負になるまでのデータを集める
        # また、もしキューの数を超えてデータを探索してしまったら、そこで探索終了
        if over_flag and (data.accel_x < 0 or counter > len(data_queue)):
            # 台形積分で速度を求める
            velocity = 0
            dq = list(data_queue)
            for i in range(1, len(dq)):
                # 前後の値が0未満ならば0にする
                a0 = max(dq[i - 1].accel_x, 0)
                a1 = max(dq[i].accel_x, 0)

                # 加速度をm/s^2に変換
                a0 = a0 * G
                a1 = a1 * G

                # 前後のタイムスリップを取得
                t0 = dq[i - 1].timestamp
                t1 = dq[i].timestamp

                # 差を計算しつつ、m/sに変換
                dt = (t1 - t0) / 1000  # ms→s

                velocity += (a0 + a1) * dt / 2  # G 2 m/s^2

                # 積分した範囲のreceived_atを保存してグラフに重ねるためにリストに追加
                created_at_list.append(dq[i].received_at)

            print(
                f"取得したデータの速度: {velocity:.2f} m/s, fixed: {convert_and_trim(velocity):.2f} m/s"
            )
            over_flag = False

    # x軸: received_at（相対時間[s]）
    x_axis = [data.received_at for data in all_data if data.received_at is not None]
    x_axis = [x.timestamp() for x in x_axis]
    x_axis = [x - x_axis[0] for x in x_axis]

    # ジャイロ値を抽出
    gx = [data.gyro_x for data in all_data]
    gy = [data.gyro_y for data in all_data]
    gz = [data.gyro_z for data in all_data]
    gz_raw = [data.gyro_raw_z for data in all_data]
    motor_angle = [data.motor_angle for data in all_data]

    # 加速度値を抽出
    ax = [data.accel_x for data in all_data]
    ay = [data.accel_y for data in all_data]
    az = [data.accel_z for data in all_data]

    # 各軸のジャイロにLPFをかける
    alpha = 0.5
    gx_filtered = lowpass_filter(gx, alpha=alpha)
    gy_filtered = lowpass_filter(gy, alpha=alpha)
    gz_filtered = lowpass_filter(gz, alpha=alpha)

    fig, axs = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

    # 上段: ジャイロ
    axs[0].plot(x_axis, gx, label="gx")
    axs[0].plot(x_axis, gy, label="gy")
    axs[0].plot(x_axis, gz, label="gz")
    # axs[0].plot(x_axis, gz_filtered, label="gz_filtered", alpha=0.7, linewidth=0.3)
    axs[0].set_ylabel("Angular Velocity [deg/s]")
    axs[0].set_title("Stone Data (Gyro)")
    axs[0].legend()
    axs[0].grid(True)

    # 下段: 加速度
    axs[1].scatter(x_axis, ax, label="ax", s=10)
    axs[1].scatter(x_axis, ay, label="ay", s=10)
    # axs[1].scatter(x_axis, az, label="az", s=10)
    axs[1].set_xlabel("received_at [s]")
    axs[1].set_ylabel("Acceleration [m/s^2]")
    axs[1].set_title("Stone Data (Accel)")
    axs[1].legend()
    axs[1].grid(True)

    # 0.1にラインを追加
    axs[1].axhline(y=0.1, color="r", linestyle="--", label="0.1G Line")
    axs[1].legend()

    # created_at_listをグラフに示すために、timestampに変換したうえでx_axis[0]を引いて時間軸を合わせる
    created_at_times = [
        created_at.timestamp() - all_data[0].received_at.timestamp()
        for created_at in created_at_list
    ]

    for created_at in created_at_times:
        axs[1].axvline(x=created_at, color="g", linestyle="--", linewidth=0.5)

    plt.tight_layout()

    # xlim
    # plt.xlim(402, 404)

    print("Plot saved as stone_plot.svg")
    plt.savefig(graph_save_path / "stone_plot.svg")

    print(f"全データ件数: {len(all_data)}")


if __name__ == "__main__":
    main()
