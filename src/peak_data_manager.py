import pathlib
import asyncio
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel
from sqlalchemy import (
    select,
    delete,
    desc,
    Integer,
    Float,
    DateTime,
    BigInteger,
    Column,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

try:
    from .db import get_engine_by_path
except ImportError:
    import sys
    import pathlib

    # 相対パスでdbモジュールをインポート
    current_dir = pathlib.Path(__file__).parent
    sys.path.append(str(current_dir))
    from db import get_engine_by_path

# 投球ピークデータ用のBase
PeakBase = declarative_base()


class PeakDataModel(BaseModel):
    """投球ピークデータのPydanticモデル"""

    # ID（DBから取得時のみ使用）
    id: Optional[int] = None
    throw_id: int  # 投球ID

    # 基本情報
    timestamp: int  # ミリ秒タイムスタンプ
    counter: int
    received_at: Optional[datetime] = None  # 受信時刻

    # モーターデータ
    motor_angle: float
    motor_speed: float  # RPM
    motor_current: float  # アンペア
    motor_temp: int  # 摂氏
    motor_torque: int

    # 制御データ
    control_target_rpm: int
    control_current_rpm: float
    control_output_current: float
    control_error: float

    # 加速度データ (G)
    accel_x: float
    accel_y: float
    accel_z: float

    # ジャイロデータ (deg/s)
    gyro_x: float
    gyro_y: float
    gyro_z: float
    gyro_raw_z: float

    class Config:
        from_attributes = True


class ThrowPeakDataDB(PeakBase):
    """投球ピークデータ用のSQLAlchemyモデル"""

    __tablename__ = "throw_peak_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    throw_id = Column(Integer, nullable=False)  # 投球ID

    # 基本情報
    timestamp = Column(BigInteger, nullable=False)  # ミリ秒タイムスタンプ
    counter = Column(Integer, nullable=False)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # モーターデータ
    motor_angle = Column(Float, nullable=False)
    motor_speed = Column(Float, nullable=False)  # RPM
    motor_current = Column(Float, nullable=False)  # アンペア
    motor_temp = Column(Integer, nullable=False)  # 摂氏
    motor_torque = Column(Integer, nullable=False)

    # 制御データ
    control_target_rpm = Column(Integer, nullable=False)
    control_current_rpm = Column(Float, nullable=False)
    control_output_current = Column(Float, nullable=False)
    control_error = Column(Float, nullable=False)

    # 加速度データ (G)
    accel_x = Column(Float, nullable=False)
    accel_y = Column(Float, nullable=False)
    accel_z = Column(Float, nullable=False)

    # ジャイロデータ (deg/s)
    gyro_x = Column(Float, nullable=False)
    gyro_y = Column(Float, nullable=False)
    gyro_z = Column(Float, nullable=False)
    gyro_raw_z = Column(Float, nullable=False)

    class Config:
        from_attributes = True


class PeakDataManager:
    """投球ピークデータの管理クラス"""

    def __init__(self, db_path: Optional[pathlib.Path] = None):
        if db_path is None:
            # デフォルトDB
            project_root = pathlib.Path(__file__).parents[1]
            db_path = project_root / "data" / "throw_peak_data.sqlite3"
        self.engine = get_engine_by_path(db_path)

    async def create_table(self) -> None:
        """テーブルを作成する関数"""
        async with self.engine.begin() as conn:
            await conn.run_sync(PeakBase.metadata.create_all)

    @staticmethod
    def convert_db_to_model(db_data) -> PeakDataModel:
        """SQLAlchemyのDBレコードをPydanticモデルに変換"""
        # Rowオブジェクトの場合は row[0] でモデル本体を取得
        obj = db_data[0] if hasattr(db_data, "__getitem__") else db_data
        return PeakDataModel.model_validate(obj)

    async def get_throw_ids(self) -> List[int]:
        """利用可能な投球IDのリストを取得する"""
        async with AsyncSession(self.engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = (
                    select(ThrowPeakDataDB.throw_id)
                    .distinct()
                    .order_by(ThrowPeakDataDB.throw_id)
                )
                result = await session.execute(stmt)
                throw_ids = [row[0] for row in result.fetchall()]
                return throw_ids

    async def get_data_by_throw_id(self, throw_id: int) -> List[PeakDataModel]:
        """指定した投球IDのデータを取得する"""
        async with AsyncSession(self.engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = (
                    select(ThrowPeakDataDB)
                    .where(ThrowPeakDataDB.throw_id == throw_id)
                    .order_by(ThrowPeakDataDB.timestamp)
                )
                result = await session.execute(stmt)
                rows = result.fetchall()
                return [self.convert_db_to_model(row) for row in rows]

    async def get_latest_data(self, limit: int = 100) -> List[PeakDataModel]:
        """最新のデータを取得する"""
        async with AsyncSession(self.engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = (
                    select(ThrowPeakDataDB)
                    .order_by(desc(ThrowPeakDataDB.received_at))
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.fetchall()
                return [self.convert_db_to_model(row) for row in rows]

    async def get_data_count_by_throw_id(self, throw_id: int) -> int:
        """指定した投球IDのデータ数を取得する"""
        async with AsyncSession(self.engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = select(ThrowPeakDataDB.id).where(
                    ThrowPeakDataDB.throw_id == throw_id
                )
                result = await session.execute(stmt)
                return len(result.fetchall())

    async def get_all_data(self) -> List[PeakDataModel]:
        """全データを取得する"""
        async with AsyncSession(self.engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = select(ThrowPeakDataDB).order_by(
                    ThrowPeakDataDB.throw_id, ThrowPeakDataDB.timestamp
                )
                result = await session.execute(stmt)
                rows = result.fetchall()
                return [self.convert_db_to_model(row) for row in rows]

    async def delete_throw_data(self, throw_id: int) -> int:
        """指定した投球IDのデータを削除する"""
        async with AsyncSession(self.engine) as session:
            async with session.begin():
                stmt = delete(ThrowPeakDataDB).where(
                    ThrowPeakDataDB.throw_id == throw_id
                )
                result = await session.execute(stmt)
                return result.rowcount


if __name__ == "__main__":
    # テスト用のコード
    async def test_peak_data_manager():
        manager = PeakDataManager()
        await manager.create_table()

        # 投球IDリスト取得テスト
        throw_ids = await manager.get_throw_ids()
        print(f"Available throw IDs: {throw_ids}")

        if throw_ids:
            # 最初の投球IDのデータを取得
            first_throw_id = throw_ids[0]
            data = await manager.get_data_by_throw_id(first_throw_id)
            print(f"Throw ID {first_throw_id} has {len(data)} records")

        # 全データ数取得
        all_data = await manager.get_all_data()
        print(f"Total records: {len(all_data)}")

    asyncio.run(test_peak_data_manager())
