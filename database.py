from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, select, delete, Index

DB_URL = "sqlite+aiosqlite:///finance.db"
Base = declarative_base()


class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    date = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index('idx_user_date', 'user_id', 'date'),
    )


class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    timezone = Column(String, nullable=True, default="Europe/Moscow")
    created_at = Column(DateTime, default=datetime.utcnow)


class RecurringPayment(Base):
    __tablename__ = "recurring_payments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    day_of_month = Column(Integer, nullable=False)
    active = Column(Boolean, default=True)
    last_triggered = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


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

        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            user = User(user_id=user_id)
            session.add(user)

        await session.commit()


async def delete_last_expense(user_id: int):
    async with AsyncSessionLocal() as session:
        stmt = select(Expense).where(
            Expense.user_id == user_id
        ).order_by(Expense.date.desc()).limit(1)
        result = await session.execute(stmt)
        expense = result.scalar_one_or_none()
        if expense:
            amount = expense.amount
            category = expense.category
            await session.delete(expense)
            await session.commit()
            return {"amount": amount, "category": category}
        return None


async def get_user_timezone(user_id: int) -> str:
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user and user.timezone:
            return user.timezone
        return "Europe/Moscow"


async def set_user_timezone(user_id: int, timezone: str):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            user = User(user_id=user_id, timezone=timezone)
            session.add(user)
        else:
            user.timezone = timezone
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

        stmt = select(Expense).where(
            Expense.user_id == user_id,
            Expense.date >= start
        ).order_by(Expense.date.desc())

        result = await session.execute(stmt)
        expenses = result.scalars().all()
        return expenses


async def get_expenses_by_date_range(user_id: int, start_date: datetime, end_date: datetime):
    async with AsyncSessionLocal() as session:
        stmt = select(Expense).where(
            Expense.user_id == user_id,
            Expense.date >= start_date,
            Expense.date <= end_date
        ).order_by(Expense.date.desc())

        result = await session.execute(stmt)
        expenses = result.scalars().all()
        return expenses


async def get_user_info(user_id: int):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        return user


async def update_user_info(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(user)
        else:
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name

        await session.commit()
        return user


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

        stmt = delete(Expense).where(
            Expense.user_id == user_id,
            Expense.date >= start
        )
        await session.execute(stmt)
        await session.commit()


async def get_period_total(user_id: int, start: datetime, end: datetime) -> float:
    async with AsyncSessionLocal() as session:
        stmt = select(Expense).where(
            Expense.user_id == user_id,
            Expense.date >= start,
            Expense.date <= end
        )
        result = await session.execute(stmt)
        expenses = result.scalars().all()
        return sum(e.amount for e in expenses)


async def get_category_totals(user_id: int, start: datetime, end: datetime) -> dict:
    async with AsyncSessionLocal() as session:
        stmt = select(Expense).where(
            Expense.user_id == user_id,
            Expense.date >= start,
            Expense.date <= end
        )
        result = await session.execute(stmt)
        expenses = result.scalars().all()
        totals = {}
        for e in expenses:
            totals[e.category] = totals.get(e.category, 0) + e.amount
        return totals


async def get_weekday_totals(user_id: int, start: datetime, end: datetime) -> dict:
    async with AsyncSessionLocal() as session:
        stmt = select(Expense).where(
            Expense.user_id == user_id,
            Expense.date >= start,
            Expense.date <= end
        )
        result = await session.execute(stmt)
        expenses = result.scalars().all()
        totals = {i: 0.0 for i in range(7)}
        for e in expenses:
            totals[e.date.weekday()] += e.amount
        return totals


async def add_recurring_payment(user_id: int, name: str, amount: float,
                                 category: str, day_of_month: int) -> RecurringPayment:
    async with AsyncSessionLocal() as session:
        payment = RecurringPayment(
            user_id=user_id,
            name=name,
            amount=amount,
            category=category,
            day_of_month=day_of_month,
            active=True,
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        return payment


async def get_recurring_payments(user_id: int) -> list:
    async with AsyncSessionLocal() as session:
        stmt = select(RecurringPayment).where(
            RecurringPayment.user_id == user_id,
            RecurringPayment.active == True
        ).order_by(RecurringPayment.day_of_month)
        result = await session.execute(stmt)
        return result.scalars().all()


async def delete_recurring_payment(payment_id: int, user_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        stmt = select(RecurringPayment).where(
            RecurringPayment.id == payment_id,
            RecurringPayment.user_id == user_id
        )
        result = await session.execute(stmt)
        payment = result.scalar_one_or_none()
        if payment:
            await session.delete(payment)
            await session.commit()
            return True
        return False


async def get_due_recurring_payments(now: datetime) -> list:
    async with AsyncSessionLocal() as session:
        stmt = select(RecurringPayment).where(
            RecurringPayment.active == True,
            RecurringPayment.day_of_month == now.day
        )
        result = await session.execute(stmt)
        payments = result.scalars().all()

        due = []
        for p in payments:
            if p.last_triggered is None:
                due.append(p)
            else:
                lt = p.last_triggered
                if lt.year != now.year or lt.month != now.month:
                    due.append(p)
        return due


async def mark_recurring_triggered(payment_id: int, triggered_at: datetime):
    async with AsyncSessionLocal() as session:
        stmt = select(RecurringPayment).where(RecurringPayment.id == payment_id)
        result = await session.execute(stmt)
        payment = result.scalar_one_or_none()
        if payment:
            payment.last_triggered = triggered_at
            await session.commit()


async def get_all_active_users() -> list:
    async with AsyncSessionLocal() as session:
        stmt = select(RecurringPayment.user_id).where(
            RecurringPayment.active == True
        ).distinct()
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]
