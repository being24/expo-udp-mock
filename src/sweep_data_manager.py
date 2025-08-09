import asyncio
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy.schema import Column
from sqlalchemy.sql.sqltypes import DateTime, Float, Integer

try:
    from db import engine
except ImportError:
    import pathlib
    import sys

    current_dir = pathlib.Path(__file__).parent
    sys.path.append(str(current_dir))
    from db import engine

Base = declarative_base()


class SweepDataModel(BaseModel):
    ax: float
    ay: float
    az: float
    pressure: int
    received_at: Optional[datetime] = None
    counter: Optional[int] = None

    class Config:
        from_attributes = True


class SweepDataDB(Base):
    __tablename__ = "sweep_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ax = Column(Float)
    ay = Column(Float)
    az = Column(Float)
    pressure = Column(Integer)
    received_at = Column(DateTime, default=datetime.utcnow)
    counter = Column(Integer)


class SweepDataManager:
    async def create_table(self) -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @staticmethod
    def convert_json_to_model(json_data: dict) -> SweepDataModel:
        return SweepDataModel(
            ax=json_data.get("ax", 0.0),
            ay=json_data.get("ay", 0.0),
            az=json_data.get("az", 0.0),
            pressure=json_data.get("pressure", 0),
            received_at=json_data.get("received_at", None),
            counter=json_data.get("counter", None),
        )

    @staticmethod
    def convert_model_to_db(model: SweepDataModel) -> SweepDataDB:
        return SweepDataDB(
            ax=model.ax,
            ay=model.ay,
            az=model.az,
            pressure=model.pressure,
            received_at=model.received_at or datetime.utcnow(),
            counter=model.counter if model.counter is not None else 0,
        )

    @staticmethod
    def convert_db_to_model(db_data) -> SweepDataModel:
        # Rowオブジェクトの場合は row[0] でモデル本体を取得
        obj = db_data[0] if hasattr(db_data, "__getitem__") else db_data
        return SweepDataModel.model_validate(obj)

    async def save(self, data: dict):
        async with AsyncSession(engine) as session:
            async with session.begin():
                model = self.convert_json_to_model(data)
                db_data = self.convert_model_to_db(model)
                session.add(db_data)

    async def get_latest(self, limit: int = 100) -> None | list[SweepDataModel]:
        async with AsyncSession(engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = (
                    select(SweepDataDB)
                    .order_by(desc(SweepDataDB.received_at))
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.fetchall()

                if not rows:
                    return None

                return [self.convert_db_to_model(row) for row in rows]

    async def get_all_data(self) -> list[SweepDataModel]:
        async with AsyncSession(engine, expire_on_commit=True) as session:
            async with session.begin():
                stmt = select(SweepDataDB)
                result = await session.execute(stmt)
                rows = result.fetchall()

                if not rows:
                    return []

                return [self.convert_db_to_model(row) for row in rows]


if __name__ == "__main__":

    async def test():
        manager = SweepDataManager()
        await manager.create_table()
        test_json = {
            "ax": 1.23,
            "ay": 4.56,
            "az": 7.89,
            "pressure": 1012,
            "counter": 42,
        }
        # JSON→Model→DB→保存
        model = manager.convert_json_to_model(test_json)
        db_data = manager.convert_model_to_db(model)
        print(
            f"Model: {model}\nDB: ax={db_data.ax}, ay={db_data.ay}, az={db_data.az}, pressure={db_data.pressure}, counter={db_data.counter}"
        )
        await manager.save(test_json)
        print("Test data saved.")
        latest = await manager.get_latest(1)
        if latest:
            row = latest[0]
            print(f"Latest Model: {row}")

    asyncio.run(test())
