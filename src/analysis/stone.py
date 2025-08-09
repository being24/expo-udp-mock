import asyncio
import pathlib
import sys
from typing import List

import matplotlib.pyplot as plt
import numpy as np

# パスを追加してデータマネージャをimport
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))
from throw_data_manager import ThrowDataManager, SensorDataModel


def lowpass_filter(data, alpha=0.5):
    y = [data[0]]
    for x in data[1:]:
        y.append(alpha * x + (1 - alpha) * y[-1])
    return y


def main():
    # ThrowDataManagerのインスタンス化
    manager = ThrowDataManager()

    # グラフ保存パス
    graph_save_path = pathlib.Path(__file__).resolve().parents[2] / "graphs"
    if not graph_save_path.exists():
        graph_save_path.mkdir(parents=True)

    # sweep_dataテーブルの全データを取得
    all_data: List[SensorDataModel] = asyncio.run(manager.get_all_data())

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

    # 各軸のジャイロにLPFをかける
    alpha = 0.5
    gx_filtered = lowpass_filter(gx, alpha=alpha)
    gy_filtered = lowpass_filter(gy, alpha=alpha)
    gz_filtered = lowpass_filter(gz, alpha=alpha)

    # 合成角速度を計算
    composite_gyro = np.sqrt(np.array(gx) ** 2 + np.array(gy) ** 2 + np.array(gz) ** 2)
    composite_gyro_filtered = lowpass_filter(composite_gyro, alpha=alpha)

    plt.figure(figsize=(12, 6))

    # plt.plot(x_axis, gx, label="gx")
    # plt.plot(x_axis, gy, label="gy")
    plt.plot(x_axis, gz, label="gz")
    plt.plot(x_axis, gz_raw, label="gz_raw")

    # plt.plot(x_axis, gx_filtered, label="gx_filtered", alpha=0.7, linewidth=0.3)
    # plt.plot(x_axis, gy_filtered, label="gy_filtered", alpha=0.7, linewidth=0.3)
    # plt.plot(x_axis, gz_filtered, label="gz_filtered", alpha=0.7, linewidth=0.3)
    # plt.plot(
    #     x_axis,
    #     composite_gyro_filtered,
    #     label="composite_gyro",
    #     alpha=0.7,    plt.plot(x_axis, motor_angle, labelmotor_angle")

    #     linewidth=0.3,
    # )

    # ylim
    plt.ylim(-30, 30)

    plt.xlabel("received_at [s]")
    plt.ylabel("Angular Velocity [deg/s]")
    plt.title("Stone Data (Gyro)")
    plt.legend()
    plt.tight_layout()

    print("Plot saved as stone_plot.svg")
    plt.savefig(graph_save_path / "stone_plot.svg")

    print(f"全データ件数: {len(all_data)}")


if __name__ == "__main__":
    main()
