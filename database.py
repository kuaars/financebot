import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, Float, String, DateTime, select, delete

DB_URL = "sqlite+aiosqlite:///finance.db"
Base = declarative_base()

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True)

engine = create_async_engine(DB_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def add_expense(user_id: int, amount: float, category: str):
    async with AsyncSessionLocal() as session:
        msk_now = datetime.now(ZoneInfo("Europe/Moscow"))
        expense = Expense(user_id=user_id, amount=amount, category=category, date=msk_now)
        session.add(expense)
        await session.commit()

async def get_expenses_by_period(user_id: int, period: str, tz: ZoneInfo):
    async with AsyncSessionLocal() as session:
        now = datetime.now(tz)

        if period == "day":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == "year":
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            return []

        stmt = select(Expense).where(Expense.user_id == user_id).where(Expense.date >= start)
        result = await session.execute(stmt)
        expenses = result.scalars().all()
        return expenses

async def reset_stats(user_id: int, period: str, tz: ZoneInfo):
    async with AsyncSessionLocal() as session:
        now = datetime.now(tz)
        if period == "day":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == "year":
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            return

        stmt = delete(Expense).where(Expense.user_id == user_id).where(Expense.date >= start)
        await session.execute(stmt)
        await session.commit()