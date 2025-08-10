import asyncio
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy.schema import Column
from sqlalchemy.sql.sqltypes import Float, Integer, DateTime
from sqlalchemy.types import BigInteger

try:
    from .db import engine
except ImportError:
    import sys
    import pathlib

    # 相対パスでdbモジュールをインポート
    current_dir = pathlib.Path(__file__).parent
    sys.path.append(str(current_dir))
    from db import engine

Base = declarative_base()


class SensorDataModel(BaseModel):
    """センサーデータのPydanticモデル"""

    # ID（DBから取得時のみ使用）
    id: Optional[int] = None

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

    # 加速度データ (G
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


class SensorDataDB(Base):
    """センサーデータのSQLAlchemyモデル"""

    __tablename__ = "stone_sensor_data"

    id = Column(Integer, primary_key=True, autoincrement=True)

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


class ThrowDataManager:
    """センサーデータの管理クラス"""

    async def create_table(self) -> None:
        """テーブルを作成する関数"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @staticmethod
    def convert_json_to_model(json_data: dict) -> SensorDataModel:
        """JSONデータをPydanticモデルに変換する関数

        Args:
            json_data (dict): 受信したJSONデータ

        Returns:
            SensorDataModel: Pydanticモデルのインスタンス
        """
        return SensorDataModel(
            timestamp=json_data["timestamp"],
            counter=json_data["counter"],
            # モーターデータ
            motor_angle=json_data["motor"]["angle"],
            motor_speed=json_data["motor"]["speed"],
            motor_current=json_data["motor"]["current"],
            motor_temp=json_data["motor"]["temp"],
            motor_torque=json_data["motor"]["torque"],
            # 制御データ
            control_target_rpm=json_data["control"]["target_rpm"],
            control_current_rpm=json_data["control"]["current_rpm"],
            control_output_current=json_data["control"]["output_current"],
            control_error=json_data["control"]["error"],
            # 加速度データ
            accel_x=json_data["accel"]["x"],
            accel_y=json_data["accel"]["y"],
            accel_z=json_data["accel"]["z"],
            # ジャイロデータ
            gyro_x=json_data["gyro"]["x"],
            gyro_y=json_data["gyro"]["y"],
            gyro_z=json_data["gyro"]["z"],
            gyro_raw_z=json_data["gyro"]["raw_z"],
        )

    @staticmethod
    def convert_model_to_db(data: SensorDataModel) -> SensorDataDB:
        """Pydantic SensorDataModelをSensorDataDBに変換する関数

        Args:
            data (SensorDataModel): Pydanticモデル

        Returns:
            SensorDataDB: SQLAlchemyモデルのインスタンス
        """
        # 明示的にidを含めずに辞書を作成
        db_instance = SensorDataDB(
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
        return db_instance

    @staticmethod
    def convert_db_to_model(db_data) -> SensorDataModel:
        # Rowオブジェクトの場合は row[0] でモデル本体を取得
        obj = db_data[0] if hasattr(db_data, "__getitem__") else db_data
        return SensorDataModel.model_validate(obj)

    async def save_sensor_data(self, json_data: dict) -> None:
        """センサーデータを保存する関数

        Args:
            json_data (dict): 受信したJSONデータ
        """
        print(f"Saving sensor data: {json_data['gyro']}")
        async with AsyncSession(engine) as session:
            async with session.begin():
                sensor_model = self.convert_json_to_model(json_data)
                print(f"Converted sensor model: {sensor_model.gyro_z}")
                db_data = self.convert_model_to_db(sensor_model)
                print(f"DB data gyro_z: {db_data.gyro_z}")
                session.add(db_data)

    async def get_latest_data(self, limit: int = 100) -> List[SensorDataModel] | None:
        async with AsyncSession(engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = (
                    select(SensorDataDB)
                    .order_by(desc(SensorDataDB.received_at))
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.fetchall()

                if not rows:
                    return None

                # 各rowは(SensorDataDB,)のタプルなのでrow[0]を渡す
                return [self.convert_db_to_model(row) for row in rows]

    async def get_data_by_counter_range(
        self, start_counter: int, end_counter: int
    ) -> List[SensorDataModel] | None:
        """カウンター範囲でセンサーデータを取得する関数

        Args:
            start_counter (int): 開始カウンター
            end_counter (int): 終了カウンター

        Returns:
            List[SensorDataModel] | None: センサーデータのリスト、存在しない場合はNone
        """
        async with AsyncSession(engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = (
                    select(SensorDataDB)
                    .where(
                        SensorDataDB.counter >= start_counter,
                        SensorDataDB.counter <= end_counter,
                    )
                    .order_by(SensorDataDB.counter)
                )
                result = await session.execute(stmt)
                rows = result.fetchall()

                if not rows:
                    return None

                return [self.convert_db_to_model(row) for row in rows]

    async def get_data_by_timestamp_range(
        self, start_timestamp: int, end_timestamp: int
    ) -> List[SensorDataModel] | None:
        """タイムスタンプ範囲でセンサーデータを取得する関数

        Args:
            start_timestamp (int): 開始タイムスタンプ（ミリ秒）
            end_timestamp (int): 終了タイムスタンプ（ミリ秒）

        Returns:
            List[SensorDataModel] | None: センサーデータのリスト、存在しない場合はNone
        """
        async with AsyncSession(engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = (
                    select(SensorDataDB)
                    .where(
                        SensorDataDB.timestamp >= start_timestamp,
                        SensorDataDB.timestamp <= end_timestamp,
                    )
                    .order_by(SensorDataDB.timestamp)
                )
                result = await session.execute(stmt)
                rows = result.fetchall()

                if not rows:
                    return None

                return [self.convert_db_to_model(row) for row in rows]

    async def delete_old_data(self, keep_count: int = 10000) -> int:
        """古いデータを削除する関数（パフォーマンス維持のため）

        Args:
            keep_count (int): 保持する件数（デフォルト: 10000）

        Returns:
            int: 削除された件数
        """
        async with AsyncSession(engine) as session:
            async with session.begin():
                # 保持すべき最小のIDを取得
                subquery = (
                    select(SensorDataDB.id)
                    .order_by(desc(SensorDataDB.received_at))
                    .limit(keep_count)
                )
                result = await session.execute(subquery)
                keep_ids = [row[0] for row in result.fetchall()]

                if not keep_ids:
                    return 0

                min_keep_id = min(keep_ids)

                # 古いデータを削除
                stmt = delete(SensorDataDB).where(SensorDataDB.id < min_keep_id)
                result = await session.execute(stmt)
                return result.rowcount

    async def get_data_count(self) -> int:
        """保存されているデータの総数を取得する関数

        Returns:
            int: データの総数
        """
        async with AsyncSession(engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = select(SensorDataDB.id)
                result = await session.execute(stmt)
                return len(result.fetchall())

    async def get_all_data(self) -> List[SensorDataModel]:
        async with AsyncSession(engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = select(SensorDataDB)
                result = await session.execute(stmt)
                rows = result.fetchall()
                return [self.convert_db_to_model(row) for row in rows]


if __name__ == "__main__":
    # テスト用のコード
    async def test_sensor_data_manager():
        manager = ThrowDataManager()
        await manager.create_table()

        # テストデータ
        test_json = {
            "motor": {
                "angle": 123.45,
                "speed": 1500,
                "current": 2.5,
                "temp": 45,
                "torque": 1000,
            },
            "control": {
                "target_rpm": 1500,
                "current_rpm": 1498.5,
                "output_current": 2.45,
                "error": -1.5,
            },
            "accel": {"x": 0.12, "y": -0.05, "z": 9.81},
            "gyro": {"x": 1.2, "y": -0.8, "z": 0.3, "raw_z": 15.7},
            "timestamp": 123456789,
            "counter": 1,
        }

        # データ保存テスト
        await manager.save_sensor_data(test_json)
        print("Test data saved successfully")

        # データ取得テスト
        latest_data = await manager.get_latest_data(1)
        if latest_data:
            print(f"Retrieved data: counter={latest_data[0].counter}")

        # データ数取得テスト
        count = await manager.get_data_count()
        print(f"Total data count: {count}")

    asyncio.run(test_sensor_data_manager())
