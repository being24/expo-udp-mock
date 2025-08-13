import asyncio
import pathlib
import sys
from collections import deque
from typing import List, Optional
from datetime import datetime

import matplotlib.pyplot as plt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

# パスを追加してデータマネージャをimport
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))
from throw_data_manager import SensorDataModel, ThrowDataManager
from peak_data_manager import PeakDataManager, ThrowPeakDataDB
from db import get_engine_by_path

# 投球データ用のBase（PeakDataManagerから使用）
ThrowBase = declarative_base()


def lowpass_filter(data, alpha=0.5):
    """
    単純な一次ローパスフィルタ。ノイズ除去用。
    Args:
        data: 入力データリスト
        alpha: フィルタ係数（0.0〜1.0）
    Returns:
        フィルタ後のデータリスト
    """
    y = [data[0]]
    for x in data[1:]:
        y.append(alpha * x + (1 - alpha) * y[-1])
    return y


def convert_and_trim(raw_vel: float) -> float:
    """
    速度値の変換・トリム処理（現状はそのまま返す）
    Args:
        raw_vel: 積分で得られた速度値
    Returns:
        変換後の速度値
    """
    double_vel = raw_vel
    return double_vel


async def save_throw_peak_data(
    peak_data: List[SensorDataModel], throw_id: int, output_db_path: pathlib.Path
):
    """
    投球ピークデータを専用DBに保存する（PeakDataManagerを使用）
    Args:
        peak_data: ピーク前後のセンサーデータ
        throw_id: 投球ID
        output_db_path: 保存先DBファイルのPath
    """
    # PeakDataManagerを使用してテーブル作成
    manager = PeakDataManager(output_db_path)
    await manager.create_table()

    # 直接データベースに保存
    engine = get_engine_by_path(output_db_path)
    async with AsyncSession(engine) as session:
        async with session.begin():
            for data in peak_data:
                throw_peak_db = ThrowPeakDataDB(
                    throw_id=throw_id,
                    timestamp=data.timestamp,
                    counter=data.counter,
                    received_at=data.received_at or datetime.utcnow(),
                    motor_angle=data.motor_angle,
                    motor_speed=data.motor_speed,
                    motor_current=data.motor_current,
                    motor_temp=data.motor_temp,
                    motor_torque=data.motor_torque,
                    control_target_rpm=data.control_target_rpm,
                    control_current_rpm=data.control_current_rpm,
                    control_output_current=data.control_output_current,
                    control_error=data.control_error,
                    accel_x=data.accel_x,
                    accel_y=data.accel_y,
                    accel_z=data.accel_z,
                    gyro_x=data.gyro_x,
                    gyro_y=data.gyro_y,
                    gyro_z=data.gyro_z,
                    gyro_raw_z=data.gyro_raw_z,
                )
                session.add(throw_peak_db)


def extract_peak_data(
    all_data: List[SensorDataModel], peak_time: datetime, window_seconds: float
) -> List[SensorDataModel]:
    """
    ピーク時刻の前後指定秒数のデータを抽出する
    Args:
        all_data: 全センサーデータ
        peak_time: ピーク時刻
        window_seconds: 前後の秒数
    Returns:
        ピーク前後のデータリスト
    """
    if not peak_time:
        return []

    peak_data = []
    peak_timestamp = peak_time.timestamp()

    for data in all_data:
        if data.received_at is None:
            continue
        data_timestamp = data.received_at.timestamp()
        if abs(data_timestamp - peak_timestamp) <= window_seconds:
            peak_data.append(data)

    return peak_data


def plot_db(
    db_path: pathlib.Path,
    graph_save_path: pathlib.Path,
    output_db_path: Optional[pathlib.Path] = None,
    start_throw_id: int = 1,
) -> int:
    """
    指定したDBファイルからデータを取得し、グラフを生成・保存する
    Args:
        db_path: 対象のsqlite3ファイルのPath
        graph_save_path: グラフ保存先ディレクトリPath
        output_db_path: 投球ピークデータ保存先DBのPath（Noneの場合は保存しない）
        start_throw_id: 開始投球ID
    Returns:
        次に使用する投球ID
    """
    manager = ThrowDataManager(db_path)
    all_data: List[SensorDataModel] = asyncio.run(manager.get_all_data())
    if not all_data:
        print(f"No data in {db_path.name}")
        return start_throw_id

    # 直近10件のデータを保持するキュー
    data_queue = deque(maxlen=10)
    over_flag = False
    counter = 0
    G = 9.81  # 重力加速度[m/s^2]
    created_at_list = []
    peak_time = None
    limen = 0.1  # 加速度のしきい値
    throw_id = start_throw_id  # 開始投球ID

    # データを順に処理し、加速度がしきい値を超えた区間の速度積分・ピーク検出
    for data in all_data:
        data_queue.append(data)
        if data.accel_x > limen:
            over_flag = True
            counter = 0
        if over_flag:
            counter += 1
        if over_flag and (data.accel_x < 0 or counter > len(data_queue)):
            velocity = 0
            dq = list(data_queue)
            for i in range(1, len(dq)):
                a0 = max(dq[i - 1].accel_x, 0)
                a1 = max(dq[i].accel_x, 0)
                a0 = a0 * G
                a1 = a1 * G
                t0 = dq[i - 1].timestamp
                t1 = dq[i].timestamp
                dt = (t1 - t0) / 1000
                velocity += (a0 + a1) * dt / 2
                if a1 > a0:
                    peak_time = dq[i].received_at
                if dq[i].received_at is not None:
                    created_at_list.append(dq[i].received_at)

            print(
                f"{db_path.name}: velocity={velocity:.2f} m/s, fixed={convert_and_trim(velocity):.2f} m/s"
            )
            print(f"{db_path.name}: peak_time={peak_time}")

            # ピーク前後0.5秒のデータを抽出して保存
            if output_db_path and peak_time:
                peak_data = extract_peak_data(all_data, peak_time, 1)
                if peak_data:
                    asyncio.run(
                        save_throw_peak_data(peak_data, throw_id, output_db_path)
                    )
                    print(
                        f"Throw {throw_id} peak data saved ({len(peak_data)} records)"
                    )
                    throw_id += 1

            over_flag = False

    # x軸: 受信時刻の相対秒
    x_axis = [data.received_at for data in all_data if data.received_at is not None]
    if x_axis:
        x_axis = [x.timestamp() for x in x_axis]
        x_axis = [x - x_axis[0] for x in x_axis]
    else:
        x_axis = []

    # 各種センサ値を抽出
    gx = [data.gyro_x for data in all_data]
    gy = [data.gyro_y for data in all_data]
    gz = [data.gyro_z for data in all_data]
    ax = [data.accel_x for data in all_data]
    ay = [data.accel_y for data in all_data]

    # グラフ描画
    fig, axs = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    # 上段: ジャイロ
    axs[0].plot(x_axis, gx, label="gx")
    axs[0].plot(x_axis, gy, label="gy")
    axs[0].plot(x_axis, gz, label="gz")
    axs[0].set_ylabel("Angular Velocity [deg/s]")
    axs[0].set_title(f"Stone Data (Gyro) [{db_path.name}]")
    axs[0].legend()
    axs[0].grid(True)

    # 下段: 加速度
    axs[1].scatter(x_axis, ax, label="ax", s=10)
    axs[1].scatter(x_axis, ay, label="ay", s=10)
    axs[1].set_xlabel("received_at [s]")
    axs[1].set_ylabel("Acceleration [m/s^2]")
    axs[1].set_title(f"Stone Data (Accel) [{db_path.name}]")
    axs[1].legend()
    axs[1].grid(True)
    axs[1].axhline(y=limen, color="r", linestyle="--", label=f"{limen}G Line")
    axs[1].legend()

    # 積分区間のreceived_atに縦線を描画
    created_at_times = []
    if all_data and created_at_list and all_data[0].received_at is not None:
        for created_at in created_at_list:
            if created_at is not None:
                created_at_times.append(
                    created_at.timestamp() - all_data[0].received_at.timestamp()
                )
        for created_at in created_at_times:
            axs[1].axvline(x=created_at, color="g", linestyle="--", linewidth=0.5)

    plt.tight_layout()
    axs[1].set_ylim(-0.5, 0.5)
    out_svg = graph_save_path / f"{db_path.stem}.svg"
    plt.savefig(out_svg)
    print(f"Plot saved as {out_svg}")
    print(f"{db_path.name}: 全データ件数: {len(all_data)}")
    plt.close(fig)

    return throw_id


def main():
    """
    dataディレクトリ内の全sqlite3ファイルに対してグラフ生成を行う
    """
    # グラフ保存パス
    graph_save_path = pathlib.Path(__file__).resolve().parents[2] / "graphs"
    if not graph_save_path.exists():
        graph_save_path.mkdir(parents=True)

    # dataディレクトリ内のsqlite3ファイルを全取得
    data_dir = pathlib.Path(__file__).resolve().parents[2] / "data"
    print(data_dir)
    # throw_peak_data.sqlite3を除外して、他のsqlite3ファイルのみ取得
    db_files = [
        f for f in data_dir.glob("*.sqlite3") if f.name != "throw_peak_data.sqlite3"
    ]
    if not db_files:
        print("No sqlite3 files found in data directory.")
        return

    # 投球ピークデータ保存用DB
    output_db_path = data_dir / "throw_peak_data.sqlite3"

    # 既存のピークデータを削除して新しく始める
    if output_db_path.exists():
        output_db_path.unlink()
        print(f"Removed existing {output_db_path.name}")

    # 全体で一意の投球ID
    global_throw_id = 1

    # 各DBごとにグラフ生成
    for db_path in db_files:
        print(f"\nProcessing {db_path.name}...")
        global_throw_id = plot_db(
            db_path, graph_save_path, output_db_path, global_throw_id
        )

    print(f"\nTotal throws processed: {global_throw_id - 1}")


if __name__ == "__main__":
    main()
