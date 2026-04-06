import logging
import logging.handlers
import os
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import asyncio
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from pdf_generator import generate_expense_report
from config import BOT_TOKEN, CATEGORIES

matplotlib.use('Agg')

LOG_DIR = "/root/financebot"
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
os.makedirs(LOG_DIR, exist_ok=True)

_log_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8"
)
_log_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

pending_expenses = {}
user_last_messages = {}
user_report_state = {}
user_confirmation_state = {}
user_last_expense = {}

MSK_TIMEZONE = ZoneInfo("Europe/Moscow")

TIMEZONES = [
    ("🏙 Москва, Санкт-Петербург (UTC+3)",  "Europe/Moscow"),
    ("🌆 Калининград (UTC+2)",               "Europe/Kaliningrad"),
    ("🏔 Самара, Ижевск (UTC+4)",            "Europe/Samara"),
    ("🏔 Екатеринбург (UTC+5)",              "Asia/Yekaterinburg"),
    ("🌃 Омск (UTC+6)",                      "Asia/Omsk"),
    ("🌃 Новосибирск, Барнаул (UTC+7)",      "Asia/Novosibirsk"),
    ("🌉 Красноярск (UTC+7)",               "Asia/Krasnoyarsk"),
    ("🌁 Иркутск (UTC+8)",                  "Asia/Irkutsk"),
    ("🌄 Якутск (UTC+9)",                   "Asia/Yakutsk"),
    ("🌅 Владивосток, Хабаровск (UTC+10)",  "Asia/Vladivostok"),
    ("🌠 Магадан (UTC+11)",                 "Asia/Magadan"),
    ("🌌 Камчатка (UTC+12)",                "Asia/Kamchatka"),
]

TEXTS = {
    "start": (
        "👋 Привет! Я помогу тебе учитывать личные расходы.\n\n"
        "💵 Просто введи сумму (например, 250) — и выбери категорию.\n\n"
        "🕐 Команда /timezone — настройка часового пояса."
    ),
    "main_menu": "📋 Главное меню:\n💵 Просто введи сумму (например, 250) — и выбери категорию.",
    "enter_amount": "💰 Введите сумму расхода (в рублях):",
    "choose_category": "📂 Выберите категорию:",
    "custom_category_prompt": "✏️ Введите название своей категории расходов:\n\n💡 Например: Такси, Кафе, Кино, Подарок и т.д.",
    "expense_added": "✅ Расход {amount:.2f} ₽ добавлен в категорию «{category}».\n\nХотите отменить?",
    "expense_cancelled": "↩️ Расход {amount:.2f} ₽ ({category}) отменён.",
    "nothing_to_cancel": "❌ Нет расхода для отмены.",
    "no_amount": "⚠️ Сначала введите сумму расхода!",
    "stats_period": "📊 Выберите период, за который показать статистику:",
    "report_menu": "📄 Выберите период для отчета (PDF):",
    "enter_start_date": "📅 Введите начальную дату в формате ДД.ММ.ГГГГ\nНапример: 01.12.2024",
    "enter_end_date": "📅 Введите конечную дату в формате ДД.ММ.ГГГГ\nНапример: 31.12.2024",
    "invalid_date": "❌ Неверный формат даты! Используйте формат ДД.ММ.ГГГГ\nПопробуйте снова:",
    "date_range_error": "❌ Начальная дата должна быть раньше конечной!",
    "generating_report": "⏳ Генерирую отчет...",
    "report_sent": "✅ Отчет отправлен!",
    "no_data_report": "📭 За выбранный период нет данных для отчета.",
    "reset_period": "🗑 Выберите период, за который очистить статистику:",
    "confirm_reset": "⚠️ <b>Вы уверены, что хотите очистить статистику за {period}?</b>\n\n❌ Это действие нельзя отменить!\n📊 Все расходы за этот период будут удалены.",
    "reset_cancelled": "❌ Очистка статистики отменена.",
    "no_data": "📉 За выбранный период расходов не найдено.",
    "no_chart_data": "📉 Нет данных для диаграммы.",
    "stats_cleared": "✅ Статистика за выбранный период очищена.",
    "category_too_long": "❌ Название категории слишком длинное! Введите до 50 символов:",
    "category_too_short": "❌ Название категории слишком короткое! Введите минимум 2 символа:",
    "zero_amount": "❌ Сумма не должна быть равной нулю! Введите другую сумму:",
    "error": "❌ Произошла ошибка. Попробуйте еще раз.",
    "choose_timezone": "🕐 Выберите ваш часовой пояс:",
    "timezone_saved": "✅ Часовой пояс сохранён:\n{tz_label}",
}

PERIOD_NAMES = {
    "day": "день",
    "week": "неделю",
    "month": "месяц",
    "year": "год"
}

async def get_user_tz(user_id: int) -> ZoneInfo:
    tz_str = await db.get_user_timezone(user_id)
    try:
        return ZoneInfo(tz_str)
    except Exception:
        return MSK_TIMEZONE

async def delete_previous_messages(user_id: int):
    if user_id in user_last_messages:
        for msg_id in user_last_messages[user_id]:
            try:
                await bot.delete_message(chat_id=user_id, message_id=msg_id)
            except Exception as e:
                logging.debug(f"Не удалось удалить сообщение: {e}")
        user_last_messages[user_id] = []

async def save_message_id(user_id: int, message_id: int):
    if user_id not in user_last_messages:
        user_last_messages[user_id] = []
    user_last_messages[user_id].append(message_id)

async def safe_edit_or_send(callback: types.CallbackQuery, text: str, reply_markup=None):
    try:
        msg = await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as e:
        logging.debug(f"Не удалось редактировать сообщение: {e}")
        msg = await callback.message.answer(text, reply_markup=reply_markup, parse_mode='HTML')
    await save_message_id(callback.from_user.id, msg.message_id)
    return msg

async def safe_send_message(user_id: int, text: str, reply_markup=None):
    try:
        msg = await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
        await save_message_id(user_id, msg.message_id)
        return msg
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")
        return None

def create_keyboard(buttons_config, adjust_count=1):
    builder = InlineKeyboardBuilder()
    for text, callback_data in buttons_config:
        builder.button(text=text, callback_data=callback_data)
    builder.adjust(adjust_count)
    return builder.as_markup()

def main_menu():
    buttons = [
        ("📊 Показать статистику", "stats_menu"),
    ]
    return create_keyboard(buttons, 2)

def category_menu():
    buttons = [(cat, f"cat:{cat}") for cat in CATEGORIES]
    buttons.append(("✏️ Своя категория", "custom_category"))
    return create_keyboard(buttons, 2)

def after_expense_menu():
    buttons = [
        ("↩️ Отменить расход", "undo_expense"),
        ("📋 Главное меню",    "back_main"),
    ]
    return create_keyboard(buttons, 2)

def stats_menu():
    buttons = [
        ("📅 За день",            "stats:day"),
        ("🗓 За неделю",          "stats:week"),
        ("📈 За месяц",           "stats:month"),
        ("📊 За год",             "stats:year"),
        ("🗑 Очистить статистику", "reset_menu"),
        ("⬅️ Назад",              "back_main")
    ]
    return create_keyboard(buttons, 2)

def report_menu():
    buttons = [
        ("📅 За день",             "report:day"),
        ("🗓 За неделю",           "report:week"),
        ("📈 За месяц",            "report:month"),
        ("📊 За год",              "report:year"),
        ("📅 Произвольный период", "report:custom"),
        ("⬅️ Назад",              "stats_menu")
    ]
    return create_keyboard(buttons, 2)

def reset_menu():
    buttons = [
        ("📅 Очистить за день",    "reset:day"),
        ("🗓 Очистить за неделю",  "reset:week"),
        ("📈 Очистить за месяц",   "reset:month"),
        ("📊 Очистить за год",     "reset:year"),
        ("⬅️ Назад",              "stats_menu")
    ]
    return create_keyboard(buttons, 2)

def confirm_reset_menu(period: str):
    buttons = [
        ("✅ Подтвердить", f"confirm_reset:{period}"),
        ("❌ Отменить",    "cancel_reset")
    ]
    return create_keyboard(buttons, 2)

def stats_result_menu(period: str):
    buttons = [
        ("📊 Диаграмма расходов", f"chart:{period}"),
        ("📄 PDF отчет",          f"report:{period}"),
        ("⬅️ Назад",              "stats_menu")
    ]
    return create_keyboard(buttons, 1)

def timezone_menu():
    buttons = [(label, f"tz:{tz}") for label, tz in TIMEZONES]
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

def parse_date(date_str: str, tz: ZoneInfo) -> datetime:
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
        )
    except ValueError:
        raise ValueError("Неверный формат даты")

def create_expense_chart(expenses, period: str, user_id: int) -> str:
    category_totals = defaultdict(float)
    for exp in expenses:
        category_totals[exp.category] += exp.amount

    if not category_totals:
        return None

    labels = list(category_totals.keys())
    sizes = list(category_totals.values())

    sorted_data = sorted(zip(labels, sizes), key=lambda x: x[1], reverse=True)
    labels = [item[0] for item in sorted_data]
    sizes = [item[1] for item in sorted_data]

    colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))
    fig, ax = plt.subplots(figsize=(12, 9))

    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        autopct=lambda pct: f'{pct:.1f}%',
        startangle=90,
        colors=colors,
        wedgeprops=dict(edgecolor='w', linewidth=1.5),
        textprops=dict(fontsize=10, fontweight='bold'),
        pctdistance=0.75
    )

    for autotext in autotexts:
        autotext.set_color('black')

    legend_labels = [f"{label}: {size:.2f} ₽" for label, size in zip(labels, sizes)]
    ax.legend(
        wedges,
        legend_labels,
        title="Категории:",
        loc="center left",
        bbox_to_anchor=(1, 0, 0.5, 1),
        fontsize=9
    )

    ax.axis("equal")

    total = sum(sizes)
    ax.text(0, 0, f"Всего:\n{total:.2f} ₽",
            ha='center', va='center',
            fontsize=12, fontweight='bold')

    period_name = PERIOD_NAMES.get(period, period)
    plt.title(f"Диаграмма расходов за {period_name}",
              fontsize=14, fontweight='bold', pad=20)

    chart_path = f"chart_{user_id}.png"
    plt.savefig(chart_path, bbox_inches='tight', dpi=100)
    plt.close(fig)

    return chart_path

async def generate_pdf_report(user_id: int, period: str = None,
                              start_date: datetime = None, end_date: datetime = None):
    tz = await get_user_tz(user_id)

    if period:
        expenses = await db.get_expenses_by_period(user_id, period, tz)
        now = datetime.now(tz)
        if period == "day":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "month":
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == "year":
            start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    else:
        expenses = await db.get_expenses_by_date_range(user_id, start_date, end_date)

    if not expenses:
        return False

    user_info = await db.get_user_info(user_id)
    username = ""
    if user_info:
        if user_info.username:
            username = f"@{user_info.username}"
        elif user_info.first_name:
            username = user_info.first_name
            if user_info.last_name:
                username += f" {user_info.last_name}"

    pdf_filename = generate_expense_report(
        user_id, expenses, start_date, end_date, username
    )

    if period:
        period_name = PERIOD_NAMES.get(period, period)
        filename = f"Отчет_за_{period_name}_{datetime.now().strftime('%d.%m.%Y')}.pdf"
    else:
        filename = f"Отчет_{start_date.strftime('%d.%m.%Y')}_{end_date.strftime('%d.%m.%Y')}.pdf"

    try:
        with open(pdf_filename, 'rb') as pdf_file:
            pdf_data = pdf_file.read()
            input_file = BufferedInputFile(pdf_data, filename=filename)
            await bot.send_document(
                chat_id=user_id,
                document=input_file,
                caption=TEXTS["report_sent"]
            )
    except Exception as e:
        logging.error(f"Ошибка отправки PDF: {e}")
        return False
    finally:
        try:
            os.remove(pdf_filename)
        except Exception:
            pass

    return True

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await delete_previous_messages(message.from_user.id)
    await db.init_db()

    user = message.from_user
    try:
        await db.update_user_info(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
    except Exception as e:
        logging.error(f"Ошибка обновления информации о пользователе: {e}")

    await safe_send_message(user.id, TEXTS["start"], main_menu())

@dp.message(Command("timezone"))
async def timezone_cmd(message: types.Message):
    await delete_previous_messages(message.from_user.id)
    await safe_send_message(message.from_user.id, TEXTS["choose_timezone"], timezone_menu())

@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await safe_edit_or_send(callback, TEXTS["main_menu"], main_menu())

@dp.callback_query(F.data.startswith("tz:"))
async def timezone_chosen(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    tz_str = callback.data[3:]

    tz_label = tz_str
    for label, tz in TIMEZONES:
        if tz == tz_str:
            tz_label = label
            break

    await db.set_user_timezone(user_id, tz_str)
    await delete_previous_messages(user_id)
    await safe_edit_or_send(
        callback,
        TEXTS["timezone_saved"].format(tz_label=tz_label),
        main_menu()
    )
    await callback.answer()

@dp.callback_query(F.data == "undo_expense")
async def undo_expense(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await delete_previous_messages(user_id)

    deleted = await db.delete_last_expense(user_id)
    user_last_expense.pop(user_id, None)

    if deleted:
        text = TEXTS["expense_cancelled"].format(
            amount=deleted["amount"],
            category=deleted["category"]
        )
    else:
        text = TEXTS["nothing_to_cancel"]

    await safe_edit_or_send(callback, text, main_menu())
    await callback.answer()

@dp.message(F.text.regexp(r"^\d+(\.\d{1,2})?$"))
async def get_amount(message: types.Message):
    await delete_previous_messages(message.from_user.id)
    user_id = message.from_user.id
    amount = float(message.text)

    if amount == 0:
        await safe_send_message(user_id, TEXTS["zero_amount"])
        return

    pending_expenses[user_id] = amount
    await safe_send_message(user_id, TEXTS["choose_category"], category_menu())

@dp.callback_query(F.data == "custom_category")
async def ask_custom_category(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id

    if user_id not in pending_expenses:
        await safe_send_message(user_id, TEXTS["no_amount"], main_menu())
        return

    await safe_edit_or_send(callback, TEXTS["custom_category_prompt"])

@dp.callback_query(F.data.startswith("cat:"))
async def category_chosen(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    category = callback.data.split(":", 1)[1]

    if user_id not in pending_expenses:
        await safe_send_message(user_id, TEXTS["no_amount"], main_menu())
        return

    amount = pending_expenses.pop(user_id)
    await db.add_expense(user_id, amount, category)
    user_last_expense[user_id] = {"amount": amount, "category": category}

    await safe_edit_or_send(
        callback,
        TEXTS["expense_added"].format(amount=amount, category=category),
        after_expense_menu()
    )

@dp.message(F.text & ~F.text.regexp(r"^\d+(\.\d{1,2})?$"))
async def handle_text_input(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id in pending_expenses:
        await delete_previous_messages(user_id)

        if len(text) > 50:
            await safe_send_message(user_id, TEXTS["category_too_long"])
            return

        if len(text) < 2:
            await safe_send_message(user_id, TEXTS["category_too_short"])
            return

        amount = pending_expenses.pop(user_id)
        await db.add_expense(user_id, amount, text)
        user_last_expense[user_id] = {"amount": amount, "category": text}

        await safe_send_message(
            user_id,
            TEXTS["expense_added"].format(amount=amount, category=text),
            after_expense_menu()
        )

    elif user_id in user_report_state:
        state = user_report_state[user_id]
        tz = await get_user_tz(user_id)

        try:
            date = parse_date(text, tz)

            if state["step"] == "start":
                user_report_state[user_id] = {
                    "step": "end",
                    "start_date": date
                }
                await safe_send_message(user_id, TEXTS["enter_end_date"])

            else:
                start_date = state["start_date"]
                end_date = date

                if start_date > end_date:
                    await safe_send_message(user_id, TEXTS["date_range_error"])
                    return

                await delete_previous_messages(user_id)
                await safe_send_message(user_id, TEXTS["generating_report"])

                success = await generate_pdf_report(
                    user_id,
                    start_date=start_date,
                    end_date=end_date
                )

                if not success:
                    await safe_send_message(user_id, TEXTS["no_data_report"])

                del user_report_state[user_id]
                await asyncio.sleep(1)
                await safe_send_message(user_id, TEXTS["main_menu"], main_menu())

        except ValueError:
            await safe_send_message(user_id, TEXTS["invalid_date"])

@dp.callback_query(F.data == "stats_menu")
async def show_stats_menu(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await safe_edit_or_send(callback, TEXTS["stats_period"], stats_menu())

@dp.callback_query(F.data.startswith("stats:"))
async def show_stats(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    period = callback.data.split(":")[1]
    tz = await get_user_tz(user_id)

    expenses = await db.get_expenses_by_period(user_id, period, tz)
    text = format_expenses_list(expenses, period)

    await safe_edit_or_send(callback, text, stats_result_menu(period))

@dp.callback_query(F.data.startswith("chart:"))
async def show_chart(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    period = callback.data.split(":")[1]
    tz = await get_user_tz(user_id)

    expenses = await db.get_expenses_by_period(user_id, period, tz)
    if not expenses:
        await safe_edit_or_send(callback, TEXTS["no_chart_data"], stats_result_menu(period))
        return

    chart_path = create_expense_chart(expenses, period, user_id)
    if not chart_path:
        await safe_edit_or_send(callback, TEXTS["no_chart_data"], stats_result_menu(period))
        return

    period_name = PERIOD_NAMES.get(period, period)

    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад к статистике", callback_data=f"delete_chart:{period}")

    msg = await bot.send_photo(
        chat_id=user_id,
        photo=FSInputFile(chart_path),
        caption=f"📊 Диаграмма расходов за {period_name}",
        reply_markup=builder.as_markup()
    )
    await save_message_id(user_id, msg.message_id)

    try:
        os.remove(chart_path)
    except Exception:
        pass

    await callback.answer()

@dp.callback_query(F.data.startswith("delete_chart:"))
async def delete_chart_and_back(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    period = callback.data.split(":")[1]
    tz = await get_user_tz(user_id)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await delete_previous_messages(user_id)
    expenses = await db.get_expenses_by_period(user_id, period, tz)
    text = format_expenses_list(expenses, period)

    await safe_send_message(user_id, text, stats_result_menu(period))
    await callback.answer()

@dp.callback_query(F.data == "report_menu")
async def show_report_menu(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await safe_edit_or_send(callback, TEXTS["report_menu"], report_menu())

@dp.callback_query(F.data.startswith("report:"))
async def handle_report_request(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    data = callback.data.split(":")

    if len(data) == 2:
        period = data[1]

        if period == "custom":
            user_report_state[user_id] = {"step": "start"}
            await safe_send_message(user_id, TEXTS["enter_start_date"])
        else:
            await safe_send_message(user_id, TEXTS["generating_report"])

            success = await generate_pdf_report(user_id, period)

            if not success:
                await safe_send_message(user_id, TEXTS["no_data_report"])

            await asyncio.sleep(1)
            await safe_send_message(user_id, TEXTS["main_menu"], main_menu())

@dp.callback_query(F.data == "reset_menu")
async def show_reset_menu(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await safe_edit_or_send(callback, TEXTS["reset_period"], reset_menu())

@dp.callback_query(F.data.startswith("reset:"))
async def reset_stats_handler(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    period = callback.data.split(":")[1]

    user_confirmation_state[user_id] = period

    period_name = PERIOD_NAMES.get(period, period)
    text = TEXTS["confirm_reset"].format(period=period_name)

    await safe_edit_or_send(callback, text, confirm_reset_menu(period))

@dp.callback_query(F.data.startswith("confirm_reset:"))
async def confirm_reset_handler(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    period = callback.data.split(":")[1]
    tz = await get_user_tz(user_id)

    if user_id not in user_confirmation_state:
        await safe_edit_or_send(callback, TEXTS["error"], stats_menu())
        return

    del user_confirmation_state[user_id]

    await db.reset_stats(user_id, period, tz)
    await safe_edit_or_send(callback, TEXTS["stats_cleared"], stats_menu())

@dp.callback_query(F.data == "cancel_reset")
async def cancel_reset_handler(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id

    if user_id in user_confirmation_state:
        del user_confirmation_state[user_id]

    await safe_edit_or_send(callback, TEXTS["reset_cancelled"], stats_menu())

@dp.error()
async def error_handler(exception: Exception):
    logging.error(f"Ошибка в обработчике: {exception}", exc_info=True)
    return True

async def main():
    await db.init_db()
    logging.info("Бот запущен!")

    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logging.info("Бот остановлен")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
