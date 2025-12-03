import logging
import os
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import asyncio
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from config import BOT_TOKEN, CATEGORIES

matplotlib.use('Agg')

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

pending_expenses = []
user_last_messages = {}
user_waiting_for_category = {}

MSK_TIMEZONE = ZoneInfo("Europe/Moscow")

TEXTS = {
    "start": "👋 Привет! Я помогу тебе учитывать личные расходы.\n\n💵 Просто введи сумму (например, 250) — и выбери категорию.",
    "main_menu": "📋 Главное меню:\n💵 Просто введи сумму (например, 250) — и выбери категорию.",
    "enter_amount": "💰 Введите сумму расхода (в рублях):",
    "choose_category": "📂 Выберите категорию:",
    "custom_category_prompt": "✏️ Введите название своей категории расходов:\n\n💡 Например: Такси, Кафе, Кино, Подарок и т.д.",
    "expense_added": "✅ Расход {amount:.2f} ₽ добавлен в категорию «{category}».",
    "no_amount": "⚠️ Сначала введите сумму расхода!",
    "stats_period": "📊 Выберите период, за который показать статистику:",
    "reset_period": "🗑 Выберите период, за который очистить статистику:",
    "no_data": "📉 За выбранный период расходов не найдено.",
    "no_chart_data": "📉 Нет данных для диаграммы.",
    "stats_cleared": "✅ Статистика за выбранный период очищена.",
    "category_too_long": "❌ Название категории слишком длинное! Введите до 50 символов:",
    "category_too_short": "❌ Название категории слишком короткое! Введите минимум 2 символа:",
    "zero_amount": "❌ Сумма не должна быть равной нулю! Введите другую сумму:"
}

PERIOD_NAMES = {
    "day": "день",
    "week": "неделю",
    "month": "месяц",
    "year": "год"
}

async def delete_previous_messages(user_id: int):
    if user_id in user_last_messages:
        for msg_id in user_last_messages[user_id]:
            try:
                await bot.delete_message(chat_id=user_id, message_id=msg_id)
            except Exception:
                pass
        user_last_messages[user_id] = []

async def save_message_id(user_id: int, message_id: int):
    if user_id not in user_last_messages:
        user_last_messages[user_id] = []
    user_last_messages[user_id].append(message_id)

async def safe_edit_or_send(callback, text: str, reply_markup=None):
    try:
        msg = await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        msg = await callback.message.answer(text, reply_markup=reply_markup)

    await save_message_id(callback.from_user.id, msg.message_id)
    return msg

async def safe_send_message(user_id: int, text: str, reply_markup=None):
    msg = await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)
    await save_message_id(user_id, msg.message_id)
    return msg

def create_keyboard(buttons_config, adjust_count=1):
    builder = InlineKeyboardBuilder()

    for text, callback_data in buttons_config:
        builder.button(text=text, callback_data=callback_data)

    builder.adjust(adjust_count)
    return builder.as_markup()

def main_menu():
    buttons = [
        ("📊 Показать статистику", "stats_menu")
    ]
    return create_keyboard(buttons, 1)

def category_menu():
    buttons = [(cat, f"cat:{cat}") for cat in CATEGORIES]
    buttons.append(("✏️ Своя категория", "custom_category"))
    return create_keyboard(buttons, 2)

def stats_menu():
    buttons = [
        ("📅 За день", "stats:day"),
        ("🗓 За неделю", "stats:week"),
        ("📈 За месяц", "stats:month"),
        ("📊 За год", "stats:year"),
        ("🗑 Очистить статистику", "reset_menu"),
        ("⬅️ Назад", "back_main")
    ]
    return create_keyboard(buttons, 2)

def reset_menu():
    buttons = [
        ("📅 Очистить за день", "reset:day"),
        ("🗓 Очистить за неделю", "reset:week"),
        ("📈 Очистить за месяц", "reset:month"),
        ("📊 Очистить за год", "reset:year"),
        ("⬅️ Назад", "stats_menu")
    ]
    return create_keyboard(buttons, 2)

def stats_result_menu(period: str):
    buttons = [
        (f"📊 Диаграмма расходов", f"chart:{period}"),
        ("⬅️ Назад", "stats_menu")
    ]
    return create_keyboard(buttons, 1)

def back_only_menu():
    buttons = [
        ("⬅️ Назад", "stats_menu")
    ]
    return create_keyboard(buttons, 1)

def format_expenses_list(expenses, period: str) -> str:
    if not expenses:
        return TEXTS["no_data"]

    total = sum(exp.amount for exp in expenses)
    period_name = PERIOD_NAMES.get(period, period)

    lines = [
        f"• {exp.category}: {exp.amount:.2f} ₽ ({exp.date.strftime('%d.%m.%Y %H:%M')})"
        for exp in expenses
    ]

    return (
            f"📊 Статистика за {period_name}:\n\n"
            + "\n".join(lines)
            + f"\n\n💰 Итого: {total:.2f} ₽"
    )

def create_expense_chart(expenses, period: str, user_id: int) -> str:
    category_totals = defaultdict(float)
    for exp in expenses:
        category_totals[exp.category] += exp.amount

    labels = list(category_totals.keys())
    sizes = list(category_totals.values())

    sorted_data = sorted(zip(labels, sizes), key=lambda x: x[1], reverse=True)
    labels = [item[0] for item in sorted_data]
    sizes = [item[1] for item in sorted_data]

    colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))
    fig, ax = plt.subplots(figsize=(16, 12))

    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct=lambda pct: f'{pct:.1f}%',
        startangle=90,
        colors=colors,
        wedgeprops=dict(edgecolor='w', linewidth=2),
        textprops=dict(fontsize=12, fontweight='bold', color='white'),
        pctdistance=0.8
    )

    for autotext in autotexts:
        autotext.set_fontweight('bold')
        autotext.set_fontsize(11)
        autotext.set_color('black')

    legend_labels = [f"{label}\n{size:.2f} ₽" for label, size in zip(labels, sizes)]
    ax.legend(
        wedges,
        legend_labels,
        title="Категории:",
        loc="center left",
        bbox_to_anchor=(1.1, 0, 0.5, 1),
        fontsize=10,
        title_fontsize=12,
        frameon=True,
        fancybox=True,
        shadow=True
    )

    ax.axis("equal")

    total = sum(sizes)
    centre_circle = plt.Circle((0, 0), 0.6, fc='white', edgecolor='gray', linewidth=2)
    fig.gca().add_artist(centre_circle)

    ax.text(0, 0.1, "ВСЕГО", ha='center', va='center',
            fontsize=16, fontweight='bold', color='darkblue')
    ax.text(0, -0.1, f"{total:.2f} ₽", ha='center', va='center',
            fontsize=18, fontweight='bold', color='darkgreen')

    period_name = PERIOD_NAMES.get(period, period)
    plt.title(f"📊 ДИАГРАММА РАСХОДОВ\nЗА {period_name.upper()}",
              fontsize=18, fontweight='bold', pad=30, color='darkblue')

    chart_path = f"chart_{user_id}.png"
    plt.savefig(chart_path, bbox_inches='tight', dpi=150, facecolor='white')
    plt.close(fig)

    return chart_path

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await delete_previous_messages(message.from_user.id)
    await db.init_db()

    msg = await message.answer(TEXTS["start"], reply_markup=main_menu())
    await save_message_id(message.from_user.id, msg.message_id)

@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await safe_edit_or_send(callback, TEXTS["main_menu"], main_menu())

@dp.callback_query(F.data == "add_expense")
async def ask_amount(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await safe_edit_or_send(callback, TEXTS["enter_amount"])

@dp.message(F.text.regexp(r"^\d+(\.\d{1,2})?$"))
async def get_amount(message: types.Message):
    await delete_previous_messages(message.from_user.id)
    user_id = message.from_user.id
    amount = float(message.text)

    if amount == 0:
        await safe_send_message(user_id, TEXTS["zero_amount"])
        return

    pending_expenses.append((user_id, amount))
    await safe_send_message(user_id, TEXTS["choose_category"], category_menu())

@dp.callback_query(F.data == "custom_category")
async def ask_custom_category(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id

    amount = next((amt for uid, amt in pending_expenses if uid == user_id), None)

    if amount is None:
        await safe_send_message(user_id, TEXTS["no_amount"], main_menu())
        return

    user_waiting_for_category[user_id] = amount
    await safe_edit_or_send(callback, TEXTS["custom_category_prompt"])

@dp.message(F.text & ~F.text.regexp(r"^\d+(\.\d{1,2})?$"))
async def get_custom_category(message: types.Message):
    user_id = message.from_user.id

    if user_id not in user_waiting_for_category:
        return

    await delete_previous_messages(user_id)

    category = message.text.strip()
    amount = user_waiting_for_category[user_id]
    del user_waiting_for_category[user_id]

    pending_expenses[:] = [(uid, amt) for uid, amt in pending_expenses if not (uid == user_id and amt == amount)]

    if len(category) > 50:
        await safe_send_message(user_id, TEXTS["category_too_long"])
        user_waiting_for_category[user_id] = amount
        return

    if len(category) < 2:
        await safe_send_message(user_id, TEXTS["category_too_short"])
        user_waiting_for_category[user_id] = amount
        return

    await db.add_expense(user_id, amount, category)

    await safe_send_message(user_id, TEXTS["expense_added"].format(amount=amount, category=category))
    await asyncio.sleep(1.5)

    await delete_previous_messages(user_id)
    await safe_send_message(user_id, TEXTS["main_menu"], main_menu())

@dp.callback_query(F.data.startswith("cat:"))
async def category_chosen(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    category = callback.data.split(":", 1)[1]

    amount = None
    for idx, (uid, amt) in enumerate(pending_expenses):
        if uid == user_id:
            amount = amt
            pending_expenses.pop(idx)
            break

    if amount is None:
        await safe_send_message(user_id, TEXTS["no_amount"], main_menu())
        return

    await db.add_expense(user_id, amount, category)

    try:
        msg = await callback.message.edit_text(
            TEXTS["expense_added"].format(amount=amount, category=category)
        )
        await save_message_id(user_id, msg.message_id)
        await asyncio.sleep(1.5)
        msg = await callback.message.edit_text(TEXTS["main_menu"], reply_markup=main_menu())
        await save_message_id(user_id, msg.message_id)
    except Exception:
        msg1 = await callback.message.answer(f"✅ Расход {amount:.2f} ₽ добавлен.")
        msg2 = await callback.message.answer(TEXTS["main_menu"], reply_markup=main_menu())
        await save_message_id(user_id, msg1.message_id)
        await save_message_id(user_id, msg2.message_id)

@dp.callback_query(F.data == "stats_menu")
async def show_stats_menu(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await safe_edit_or_send(callback, TEXTS["stats_period"], stats_menu())

@dp.callback_query(F.data.startswith("stats:"))
async def show_stats(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    period = callback.data.split(":")[1]

    expenses = await db.get_expenses_by_period(user_id, period, MSK_TIMEZONE)
    text = format_expenses_list(expenses, period)

    await safe_edit_or_send(callback, text, stats_result_menu(period))

@dp.callback_query(F.data.startswith("chart:"))
async def show_chart(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    period = callback.data.split(":")[1]

    expenses = await db.get_expenses_by_period(user_id, period, MSK_TIMEZONE)
    if not expenses:
        await safe_edit_or_send(callback, TEXTS["no_chart_data"], back_only_menu())
        return

    chart_path = create_expense_chart(expenses, period, user_id)
    period_name = PERIOD_NAMES.get(period, period)

    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад к статистике", callback_data=f"delete_chart:{period}:{user_id}")

    msg = await bot.send_photo(
        chat_id=user_id,
        photo=FSInputFile(chart_path),
        caption=f"📊 Диаграмма расходов за {period_name}",
        reply_markup=kb.as_markup()
    )
    await save_message_id(user_id, msg.message_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_chart:"))
async def delete_chart_and_back(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data_parts = callback.data.split(":")
    period = data_parts[1]

    chart_path = f"chart_{user_id}.png"
    if os.path.exists(chart_path):
        os.remove(chart_path)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await delete_previous_messages(user_id)
    expenses = await db.get_expenses_by_period(user_id, period, MSK_TIMEZONE)
    text = format_expenses_list(expenses, period)

    await safe_send_message(user_id, text, stats_result_menu(period))
    await callback.answer()

@dp.callback_query(F.data == "reset_menu")
async def show_reset_menu(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await safe_edit_or_send(callback, TEXTS["reset_period"], reset_menu())

@dp.callback_query(F.data.startswith("reset:"))
async def reset_stats_handler(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    period = callback.data.split(":")[1]

    await db.reset_stats(user_id, period, MSK_TIMEZONE)
    await safe_edit_or_send(callback, TEXTS["stats_cleared"], stats_menu())

@dp.error()
async def error_handler(update: types.Update, exception: Exception):
    logging.warning(f"Ошибка: {exception}")
    return True

async def main():
    await db.init_db()
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())