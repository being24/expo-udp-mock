import asyncio
import pathlib
import sys
from typing import List

import matplotlib.pyplot as plt
import numpy as np

# add import path
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))
from sweep_data_manager import SweepDataManager, SweepDataModel


def lowpass_filter(data, alpha=0.1):
    y = [data[0]]
    for x in data[1:]:
        y.append(alpha * x + (1 - alpha) * y[-1])
    return y


def main():
    # SweepDataManagerのインスタンス化
    manager = SweepDataManager()

    # graph save path
    graph_save_path = pathlib.Path(__file__).resolve().parents[2] / "graphs"
    if not graph_save_path.exists():
        graph_save_path.mkdir(parents=True)

    # sweep_dataテーブルの全データを取得（Pydanticモデルのリストとして返る想定）
    all_data: List[SweepDataModel] = asyncio.run(manager.get_all_data())

    # matplotlibを使って、ax,ay,azをプロット、x軸はreceived_at
    x_axis = [data.received_at for data in all_data if data.received_at is not None]
    x_axis = [x.timestamp() for x in x_axis]
    x_axis = [x - x_axis[0] for x in x_axis]  # 時間を0からの相対時間に変換

    ax = [data.ax for data in all_data]
    ay = [data.ay for data in all_data]
    az = [data.az for data in all_data]

    # 各軸の加速度にLPF（ローパスフィルタ）をかける
    alpha = 0.5  # フィルタ係数
    ax_filtered = lowpass_filter(ax, alpha=alpha)
    ay_filtered = lowpass_filter(ay, alpha=alpha)
    az_filtered = lowpass_filter(az, alpha=alpha)

    # 合成加速度を計算
    composite_acc = np.sqrt(np.array(ax) ** 2 + np.array(ay) ** 2 + np.array(az) ** 2)

    composite_acc_filtered = lowpass_filter(composite_acc, alpha=alpha)

    plt.figure(figsize=(12, 6))
    # plt.plot(x_axis, ax, label="ax")
    # plt.plot(x_axis, ay, label="ay")
    # plt.plot(x_axis, az, label="az")

    plt.plot(x_axis, ax_filtered, label="ax_filtered", alpha=0.7, linewidth=0.3)
    plt.plot(x_axis, ay_filtered, label="ay_filtered", alpha=0.7, linewidth=0.3)
    plt.plot(x_axis, az_filtered, label="az_filtered", alpha=0.7, linewidth=0.3)
    plt.plot(
        x_axis, composite_acc_filtered, label="composite_acc", alpha=0.7, linewidth=0.3
    )

    plt.xlabel("received_at")
    plt.ylabel("Acceleration")
    plt.title("Sweep Data")
    plt.legend()
    plt.tight_layout()

    print("Plot saved as sweep_plot.svg")
    plt.savefig(graph_save_path / "sweep_plot.svg")

    print(f"全データ件数: {len(all_data)}")

    # データの周期を表示
    data_hz = 1 / np.mean(np.diff(x_axis)) if len(x_axis) > 1 else 0
    print(f"データの周期: {data_hz:.2f} Hz")


if __name__ == "__main__":
    main()
