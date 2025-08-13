import asyncio
import pathlib
import sys
from typing import List, Optional
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# パスを追加してデータマネージャをimport
sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))
from peak_data_manager import PeakDataManager, PeakDataModel


def setup_japanese_font():
    """日本語フォントを設定する"""
    # Noto Sans JPフォントのパスを探索
    font_paths = [
        pathlib.Path(__file__).resolve().parents[2]
        / "data"
        / "Noto_Sans_JP"
        / "static"
        / "NotoSansJP-Regular.ttf",
        pathlib.Path(__file__).resolve().parents[2]
        / "data"
        / "Noto_Sans_JP"
        / "NotoSansJP-VariableFont_wght.ttf",
    ]

    for font_path in font_paths:
        if font_path.exists():
            try:
                # フォントをmatplotlibに追加
                fm.fontManager.addfont(str(font_path))
                plt.rcParams["font.family"] = "Noto Sans JP"
                print(f"Japanese font loaded: {font_path.name}")
                return
            except Exception as e:
                print(f"Failed to load font {font_path}: {e}")

    print("Japanese font not found, using default font")


def lowpass_filter(data, alpha=0.5):
    """
    単純な一次ローパスフィルタ。ノイズ除去用。
    Args:
        data: 入力データリスト
        alpha: フィルタ係数（0.0〜1.0）
    Returns:
        フィルタ後のデータリスト
    """
    if not data:
        return []
    y = [data[0]]
    for x in data[1:]:
        y.append(alpha * x + (1 - alpha) * y[-1])
    return y


def plot_throw_peak_data(
    throw_id: int,
    peak_data: List[PeakDataModel],
    graph_save_path: pathlib.Path,
):
    """
    指定した投球IDのピークデータを描画・保存する
    Args:
        throw_id: 投球ID
        peak_data: ピークデータのリスト
        graph_save_path: グラフ保存先ディレクトリPath
    """
    if not peak_data:
        print(f"No data for throw ID {throw_id}")
        return

    # x軸: 受信時刻の相対秒
    x_axis = [data.received_at for data in peak_data if data.received_at is not None]
    if x_axis:
        x_axis = [x.timestamp() for x in x_axis]
        x_axis = [x - x_axis[0] for x in x_axis]
    else:
        x_axis = list(range(len(peak_data)))

    # 各種センサ値を抽出（必要なもののみ）
    gz = [data.gyro_z for data in peak_data]
    ax = [data.accel_x for data in peak_data]

    # グラフ描画（2段構成）
    fig, axs = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # 上段: ジャイロZ軸
    axs[0].scatter(x_axis, gz, label="gyro_z", s=20, alpha=0.8)
    axs[0].set_ylabel("Angular Velocity Z [deg/s]")
    axs[0].set_title(f"投球ピークデータ (ジャイロZ軸) [投球ID: {throw_id}]")
    axs[0].legend()
    axs[0].grid(True, alpha=0.3)
    axs[0].axhline(y=0, color="k", linestyle="-", alpha=0.3)

    # 下段: 加速度X軸
    axs[1].scatter(x_axis, ax, label="accel_x", s=20, alpha=0.8, color="red")
    axs[1].set_xlabel("Time [s]")
    axs[1].set_ylabel("Acceleration X [G]")
    axs[1].set_title(f"投球ピークデータ (加速度X軸) [投球ID: {throw_id}]")
    axs[1].legend()
    axs[1].grid(True, alpha=0.3)
    axs[1].axhline(y=0, color="k", linestyle="-", alpha=0.3)

    axs[1].set_ylim(-0.5, 1)  # Y軸の範囲を設定

    plt.tight_layout()

    # ファイル名に投球IDを含めて保存
    out_svg = graph_save_path / f"throw_peak_data_id_{throw_id}.svg"
    plt.savefig(out_svg, dpi=300, bbox_inches="tight")
    print(f"Peak data plot saved as {out_svg}")
    print(f"投球ID {throw_id}: データ件数: {len(peak_data)}")
    plt.close(fig)


async def plot_throw_by_id(
    throw_id: int,
    db_path: Optional[pathlib.Path] = None,
    graph_save_path: Optional[pathlib.Path] = None,
):
    """
    指定した投球IDのピークデータを描画する
    Args:
        throw_id: 投球ID
        db_path: DBファイルのPath（Noneの場合はデフォルト）
        graph_save_path: グラフ保存先ディレクトリPath（Noneの場合はデフォルト）
    """
    if db_path is None:
        db_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "data"
            / "throw_peak_data.sqlite3"
        )

    if graph_save_path is None:
        graph_save_path = pathlib.Path(__file__).resolve().parents[2] / "graphs"
        if not graph_save_path.exists():
            graph_save_path.mkdir(parents=True)

    # データマネージャを作成
    manager = PeakDataManager(db_path)

    try:
        # 指定した投球IDのデータを取得
        peak_data = await manager.get_data_by_throw_id(throw_id)

        if not peak_data:
            print(f"投球ID {throw_id} のデータが見つかりません")
            return

        # グラフを描画
        plot_throw_peak_data(throw_id, peak_data, graph_save_path)

    except Exception as e:
        print(f"エラーが発生しました: {e}")


async def list_available_throws(db_path: Optional[pathlib.Path] = None):
    """
    利用可能な投球IDの一覧を表示する
    Args:
        db_path: DBファイルのPath（Noneの場合はデフォルト）
    """
    if db_path is None:
        db_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "data"
            / "throw_peak_data.sqlite3"
        )

    if not db_path.exists():
        print(f"DBファイルが見つかりません: {db_path}")
        return

    # データマネージャを作成
    manager = PeakDataManager(db_path)

    try:
        # 投球IDリストを取得
        throw_ids = await manager.get_throw_ids()

        if not throw_ids:
            print("投球データが見つかりません")
            return

        print(f"利用可能な投球ID: {throw_ids}")

        # 各投球IDのデータ数も表示
        for throw_id in throw_ids:
            count = await manager.get_data_count_by_throw_id(throw_id)
            print(f"  投球ID {throw_id}: {count} 件のデータ")

    except Exception as e:
        print(f"エラーが発生しました: {e}")


def main():
    """
    メイン関数：投球ピークデータの描画
    """
    import argparse

    parser = argparse.ArgumentParser(description="投球ピークデータの描画")
    parser.add_argument("--id", type=int, help="描画する投球ID")
    parser.add_argument(
        "--list", action="store_true", help="利用可能な投球IDを一覧表示"
    )
    parser.add_argument("--db", type=str, help="DBファイルのパス")
    parser.add_argument("--output", type=str, help="グラフ出力ディレクトリのパス")

    args = parser.parse_args()

    # 日本語フォントを設定
    setup_japanese_font()

    # DBパスの設定
    db_path = None
    if args.db:
        db_path = pathlib.Path(args.db)

    # 出力パスの設定
    output_path = None
    if args.output:
        output_path = pathlib.Path(args.output)

    if args.list:
        # 投球ID一覧表示
        asyncio.run(list_available_throws(db_path))
    elif args.id is not None:
        # 指定したIDの描画
        asyncio.run(plot_throw_by_id(args.id, db_path, output_path))
    else:
        # デフォルト：利用可能な投球IDを表示
        print("使用方法:")
        print(
            "  python peak_data.py --list                    # 利用可能な投球IDを表示"
        )
        print(
            "  python peak_data.py --id 1                    # 投球ID 1のデータを描画"
        )
        print("  python peak_data.py --id 1 --output ./graphs  # 出力先を指定")
        print("")
        asyncio.run(list_available_throws(db_path))


if __name__ == "__main__":
    main()
