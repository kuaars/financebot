import logging
import logging.handlers
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import asyncio
import calendar
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
user_date_state = {}

user_recurring_state = {}

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

WEEKDAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
WEEKDAY_NAMES_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

TEXTS = {
    "start": (
        "👋 Привет! Я помогу тебе учитывать личные расходы.\n\n"
        "💵 Просто введи сумму — или фразу вроде «кофе 150», «300 такси».\n\n"
        "🕐 /timezone — настройка часового пояса\n"
        "🔁 /recurring — постоянные платежи"
    ),
    "main_menu": "📋 Главное меню:\n💵 Введите сумму или фразу вроде «такси 300».",
    "enter_amount": "💰 Введите сумму расхода (в рублях):",
    "choose_category": "📂 Выберите категорию:",
    "custom_category_prompt": "✏️ Введите название своей категории расходов:\n\n💡 Например: Такси, Кафе, Кино, Подарок и т.д.",
    "expense_added": "✅ Расход {amount:.2f} ₽ добавлен в категорию «{category}».\n\nХотите отменить?",
    "expense_cancelled": "↩️ Расход {amount:.2f} ₽ ({category}) отменён.",
    "nothing_to_cancel": "❌ Нет расхода для отмены.",
    "no_amount": "⚠️ Сначала введите сумму расхода!",
    "stats_period": "📊 Выберите период, за который показать статистику:",
    "enter_date_for_stats": "📅 Введите дату в формате ДД.ММ.ГГГГ или ДД-ММ-ГГГГ\nНапример: 25.01.2025 или 25-01-2025",
    "report_menu": "📄 Выберите период для отчета (PDF):",
    "enter_start_date": "📅 Введите начальную дату в формате ДД.ММ.ГГГГ или ДД-ММ-ГГГГ\nНапример: 01.12.2024",
    "enter_end_date": "📅 Введите конечную дату в формате ДД.ММ.ГГГГ или ДД-ММ-ГГГГ\nНапример: 31.12.2024",
    "invalid_date": "❌ Неверный формат даты!\nИспользуйте ДД.ММ.ГГГГ или ДД-ММ-ГГГГ\nПопробуйте снова:",
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
    "recurring_menu": "🔁 <b>Постоянные платежи</b>\n\nАвтоматически вносятся в расходы в указанный день месяца с напоминанием.",
    "recurring_empty": "У вас пока нет постоянных платежей.\nДобавьте первый кнопкой ниже.",
    "recurring_add_name": "📝 Введите название платежа:\n\nНапример: Горячая вода, Аренда, Интернет",
    "recurring_add_amount": "💰 Введите сумму платежа (в рублях):",
    "recurring_add_day": "📅 В какой день месяца вносить? (1-28)\n\nНапример: 22",
    "recurring_add_category": "📂 Выберите категорию для этого платежа:",
    "recurring_added": "✅ Постоянный платёж добавлен!\n\n📌 <b>{name}</b>\n💰 {amount:.2f} ₽\n📂 {category}\n📅 {day}-го числа каждого месяца",
    "recurring_deleted": "🗑 Платёж «{name}» удалён.",
    "recurring_invalid_day": "❌ День должен быть от 1 до 28. Введите снова:",
    "recurring_reminder": (
        "🔔 <b>Напоминание о постоянном платеже!</b>\n\n"
        "📌 {name}\n"
        "💰 {amount:.2f} ₽\n"
        "📂 {category}\n\n"
        "Расход автоматически добавлен в статистику."
    ),
}

PERIOD_NAMES = {
    "day": "день",
    "week": "неделю",
    "month": "месяц",
    "year": "год"
}

def smart_parse_expense(text: str):
    text = text.strip()

    amount_pattern = r'(\d+(?:[.,]\d{1,2})?)\s*(?:р(?:уб)?|₽)?'

    match = re.search(amount_pattern, text, re.IGNORECASE)
    if not match:
        return None

    amount_str = match.group(1).replace(',', '.')
    try:
        amount = float(amount_str)
    except ValueError:
        return None

    if amount <= 0:
        return None

    leftover = text[:match.start()].strip() + " " + text[match.end():].strip()
    leftover = re.sub(r'[^\w\s]', '', leftover).strip()

    category_hint = leftover if len(leftover) >= 2 else None
    return amount, category_hint

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

def parse_date_flexible(date_str: str, tz: ZoneInfo) -> datetime:
    clean = date_str.strip().replace("-", ".")
    try:
        return datetime.strptime(clean, "%d.%m.%Y").replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
        )
    except ValueError:
        raise ValueError("Неверный формат даты")

def create_keyboard(buttons_config, adjust_count=1):
    builder = InlineKeyboardBuilder()
    for text, callback_data in buttons_config:
        builder.button(text=text, callback_data=callback_data)
    builder.adjust(adjust_count)
    return builder.as_markup()

def main_menu():
    buttons = [("📊 Статистика", "stats_menu"),
               ("🔁 Платежи", "recurring_menu")]
    return create_keyboard(buttons, 2)

def quick_amount_menu(category_hint: str = None):
    builder = InlineKeyboardBuilder()
    quick_amounts = [50, 100, 200, 500, 1000, 2000]
    for a in quick_amounts:
        builder.button(text=f"{a} ₽", callback_data=f"quick_amount:{a}")
    builder.adjust(3)
    if category_hint:
        builder.button(text=f'✅ Категория: {category_hint[:20]}', callback_data=f"hint_cat:{category_hint[:50]}")
        builder.adjust(3, 1)
    return builder.as_markup()

def category_menu(show_quick: bool = False):
    buttons = [(cat, f"cat:{cat}") for cat in CATEGORIES]
    buttons.append(("✏️ Своя категория", "custom_category"))
    return create_keyboard(buttons, 2)

def category_menu_for_recurring():
    buttons = [(cat, f"rcat:{cat}") for cat in CATEGORIES]
    buttons.append(("✏️ Своя категория", "rcat_custom"))
    return create_keyboard(buttons, 2)

def after_expense_menu(has_last: bool = False):
    buttons = [("↩️ Отменить расход", "undo_expense")]
    if has_last:
        buttons.append(("🔄 Повторить", "repeat_expense"))
    buttons.append(("📋 Главное меню", "back_main"))
    return create_keyboard(buttons, 2)

def stats_menu():
    buttons = [
        ("📅 За день",              "stats:day"),
        ("🗓 За неделю",            "stats:week"),
        ("📈 За месяц",             "stats:month"),
        ("📊 За год",               "stats:year"),
        ("🔍 Выбрать день",         "stats:pick_date"),
        ("📉 Сравнение периодов",   "compare_menu"),
        ("🏆 Топ категорий",        "top_categories"),
        ("📆 По дням недели",       "weekday_stats"),
        ("🗑 Очистить",             "reset_menu"),
        ("⬅️ Назад",               "back_main"),
    ]
    return create_keyboard(buttons, 2)

def compare_menu():
    buttons = [
        ("📅 День vs вчера",       "compare:day"),
        ("🗓 Неделя vs прошлая",   "compare:week"),
        ("📈 Месяц vs прошлый",    "compare:month"),
        ("⬅️ Назад",              "stats_menu"),
    ]
    return create_keyboard(buttons, 2)

def report_menu():
    buttons = [
        ("📅 За день",             "report:day"),
        ("🗓 За неделю",           "report:week"),
        ("📈 За месяц",            "report:month"),
        ("📊 За год",              "report:year"),
        ("📅 Произвольный период", "report:custom"),
        ("⬅️ Назад",              "stats_menu"),
    ]
    return create_keyboard(buttons, 2)

def reset_menu():
    buttons = [
        ("📅 Очистить за день",   "reset:day"),
        ("🗓 Очистить за неделю", "reset:week"),
        ("📈 Очистить за месяц",  "reset:month"),
        ("📊 Очистить за год",    "reset:year"),
        ("⬅️ Назад",             "stats_menu"),
    ]
    return create_keyboard(buttons, 2)

def confirm_reset_menu(period: str):
    buttons = [
        ("✅ Подтвердить", f"confirm_reset:{period}"),
        ("❌ Отменить",    "cancel_reset"),
    ]
    return create_keyboard(buttons, 2)

def stats_result_menu(period: str):
    buttons = [
        ("📊 Диаграмма расходов", f"chart:{period}"),
        ("📄 PDF отчет",          f"report:{period}"),
        ("⬅️ Назад",              "stats_menu"),
    ]
    return create_keyboard(buttons, 1)

def date_stats_result_menu(date_str: str):
    buttons = [("⬅️ Назад", "stats_menu")]
    return create_keyboard(buttons, 1)

def timezone_menu():
    buttons = [(label, f"tz:{tz}") for label, tz in TIMEZONES]
    return create_keyboard(buttons, 1)

def recurring_list_menu(payments: list):
    builder = InlineKeyboardBuilder()
    for p in payments:
        builder.button(
            text=f"🗑 {p.name} ({p.day_of_month}-го, {p.amount:.0f}₽)",
            callback_data=f"del_recurring:{p.id}"
        )
    builder.button(text="➕ Добавить платёж", callback_data="add_recurring")
    builder.button(text="⬅️ Назад", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()

def recurring_empty_menu():
    buttons = [
        ("➕ Добавить платёж", "add_recurring"),
        ("⬅️ Назад", "back_main"),
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

def format_expenses_for_date(expenses, date: datetime) -> str:
    if not expenses:
        return TEXTS["no_data"]
    total = sum(exp.amount for exp in expenses)
    date_label = date.strftime("%d.%m.%Y")
    lines = [
        f"• {exp.category}: {exp.amount:.2f} ₽ ({exp.date.strftime('%H:%M')})"
        for exp in expenses
    ]
    return (
        f"📅 Расходы за {date_label}:\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Итого: {total:.2f} ₽"
    )

def format_comparison(period: str, cur: float, prev: float) -> str:
    period_labels = {
        "day":   ("сегодня", "вчера"),
        "week":  ("эта неделя", "прошлая неделя"),
        "month": ("этот месяц", "прошлый месяц"),
    }
    cur_label, prev_label = period_labels.get(period, ("текущий", "предыдущий"))

    if prev == 0:
        if cur == 0:
            diff_str = "Нет данных за оба периода."
        else:
            diff_str = "За предыдущий период расходов не было."
    else:
        diff = cur - prev
        pct = abs(diff) / prev * 100
        arrow = "📈 больше" if diff > 0 else "📉 меньше"
        diff_str = f"На {abs(diff):.2f} ₽ ({pct:.1f}%) {arrow}, чем {prev_label}."

    return (
        f"📊 <b>Сравнение расходов</b>\n\n"
        f"🔵 {cur_label.capitalize()}: <b>{cur:.2f} ₽</b>\n"
        f"⚪ {prev_label.capitalize()}: <b>{prev:.2f} ₽</b>\n\n"
        f"{diff_str}"
    )

def format_top_categories(totals: dict, period_label: str) -> str:
    if not totals:
        return TEXTS["no_data"]
    sorted_cats = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    total = sum(totals.values())
    lines = []
    medals = ["🥇", "🥈", "🥉"]
    for i, (cat, amt) in enumerate(sorted_cats):
        medal = medals[i] if i < 3 else f"{i+1}."
        pct = amt / total * 100
        lines.append(f"{medal} {cat}: {amt:.2f} ₽ ({pct:.1f}%)")
    return (
        f"🏆 <b>Топ категорий за {period_label}</b>\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Итого: {total:.2f} ₽"
    )

def format_weekday_stats(totals: dict) -> str:
    max_val = max(totals.values()) if any(totals.values()) else 1
    lines = []
    for wd in range(7):
        amt = totals[wd]
        bar_len = int(amt / max_val * 10) if max_val > 0 else 0
        bar = "█" * bar_len + "░" * (10 - bar_len)
        lines.append(f"{WEEKDAY_NAMES[wd]}: {bar} {amt:.0f} ₽")
    total = sum(totals.values())
    if total == 0:
        return TEXTS["no_data"]
    best_day = max(totals, key=totals.get)
    return (
        f"📆 <b>Расходы по дням недели (месяц)</b>\n\n"
        + "<code>" + "\n".join(lines) + "</code>"
        + f"\n\n🔥 Самый затратный день: <b>{WEEKDAY_NAMES_FULL[best_day]}</b>\n"
        f"💰 Всего: {total:.2f} ₽"
    )

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
    ax.legend(wedges, legend_labels, title="Категории:",
              loc="center left", bbox_to_anchor=(1, 0, 0.5, 1), fontsize=9)
    ax.axis("equal")

    total = sum(sizes)
    ax.text(0, 0, f"Всего:\n{total:.2f} ₽", ha='center', va='center',
            fontsize=12, fontweight='bold')

    period_name = PERIOD_NAMES.get(period, period)
    plt.title(f"Диаграмма расходов за {period_name}", fontsize=14, fontweight='bold', pad=20)

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

    pdf_filename = generate_expense_report(user_id, expenses, start_date, end_date, username)

    if period:
        period_name = PERIOD_NAMES.get(period, period)
        filename = f"Отчет_за_{period_name}_{datetime.now().strftime('%d.%m.%Y')}.pdf"
    else:
        filename = f"Отчет_{start_date.strftime('%d.%m.%Y')}_{end_date.strftime('%d.%m.%Y')}.pdf"

    try:
        with open(pdf_filename, 'rb') as pdf_file:
            pdf_data = pdf_file.read()
            input_file = BufferedInputFile(pdf_data, filename=filename)
            await bot.send_document(chat_id=user_id, document=input_file,
                                    caption=TEXTS["report_sent"])
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
        await db.update_user_info(user_id=user.id, username=user.username,
                                  first_name=user.first_name, last_name=user.last_name)
    except Exception as e:
        logging.error(f"Ошибка обновления пользователя: {e}")
    await safe_send_message(user.id, TEXTS["start"], main_menu())

@dp.message(Command("timezone"))
async def timezone_cmd(message: types.Message):
    await delete_previous_messages(message.from_user.id)
    await safe_send_message(message.from_user.id, TEXTS["choose_timezone"], timezone_menu())

@dp.message(Command("recurring"))
async def recurring_cmd(message: types.Message):
    await delete_previous_messages(message.from_user.id)
    await show_recurring_list(message.from_user.id)

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
    await safe_edit_or_send(callback, TEXTS["timezone_saved"].format(tz_label=tz_label), main_menu())
    await callback.answer()

@dp.callback_query(F.data.startswith("quick_amount:"))
async def quick_amount_chosen(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    amount = float(callback.data.split(":")[1])
    pending_expenses[user_id] = amount
    await safe_edit_or_send(callback, TEXTS["choose_category"], category_menu())
    await callback.answer()

@dp.callback_query(F.data.startswith("hint_cat:"))
async def hint_category_chosen(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    user_id = callback.from_user.id
    category = callback.data.split(":", 1)[1]
    if user_id not in pending_expenses:
        await safe_send_message(user_id, TEXTS["no_amount"], main_menu())
        return
    amount = pending_expenses.pop(user_id)
    await db.add_expense(user_id, amount, category)
    user_last_expense[user_id] = {"amount": amount, "category": category}
    has_last = user_id in user_last_expense
    await safe_edit_or_send(
        callback,
        TEXTS["expense_added"].format(amount=amount, category=category),
        after_expense_menu(has_last=True)
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
            amount=deleted["amount"], category=deleted["category"])
    else:
        text = TEXTS["nothing_to_cancel"]
    await safe_edit_or_send(callback, text, main_menu())
    await callback.answer()

@dp.callback_query(F.data == "repeat_expense")
async def repeat_expense(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await delete_previous_messages(user_id)
    last = user_last_expense.get(user_id)
    if not last:
        await safe_edit_or_send(callback, "❌ Нет предыдущего расхода для повтора.", main_menu())
        await callback.answer()
        return
    amount = last["amount"]
    category = last["category"]
    await db.add_expense(user_id, amount, category)
    await safe_edit_or_send(
        callback,
        f"🔄 Повторён расход: {amount:.2f} ₽ → «{category}»",
        after_expense_menu(has_last=True)
    )
    await callback.answer()

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
        after_expense_menu(has_last=True)
    )
    await callback.answer()

@dp.callback_query(F.data == "stats_menu")
async def show_stats_menu(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await safe_edit_or_send(callback, TEXTS["stats_period"], stats_menu())

@dp.callback_query(F.data.startswith("stats:"))
async def show_stats(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    period = callback.data.split(":")[1]

    if period == "pick_date":
        await delete_previous_messages(user_id)
        user_date_state[user_id] = True
        await safe_edit_or_send(callback, TEXTS["enter_date_for_stats"])
        return

    await delete_previous_messages(user_id)
    tz = await get_user_tz(user_id)
    expenses = await db.get_expenses_by_period(user_id, period, tz)
    text = format_expenses_list(expenses, period)
    await safe_edit_or_send(callback, text, stats_result_menu(period))

@dp.callback_query(F.data == "compare_menu")
async def show_compare_menu(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await safe_edit_or_send(callback, "📊 Выберите период для сравнения:", compare_menu())

@dp.callback_query(F.data.startswith("compare:"))
async def show_comparison(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    period = callback.data.split(":")[1]
    tz = await get_user_tz(user_id)
    now = datetime.now(tz)

    if period == "day":
        cur_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        cur_end = now
        prev_start = cur_start - timedelta(days=1)
        prev_end = cur_start - timedelta(seconds=1)
    elif period == "week":
        cur_start = now - timedelta(days=now.weekday())
        cur_start = cur_start.replace(hour=0, minute=0, second=0, microsecond=0)
        cur_end = now
        prev_start = cur_start - timedelta(weeks=1)
        prev_end = cur_start - timedelta(seconds=1)
    elif period == "month":
        cur_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cur_end = now
        prev_month_end = cur_start - timedelta(seconds=1)
        prev_start = prev_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_end = prev_month_end
    else:
        await callback.answer()
        return

    cur_total = await db.get_period_total(user_id, cur_start, cur_end)
    prev_total = await db.get_period_total(user_id, prev_start, prev_end)

    text = format_comparison(period, cur_total, prev_total)
    back_kb = create_keyboard([("⬅️ Назад", "compare_menu")], 1)
    await delete_previous_messages(user_id)
    await safe_edit_or_send(callback, text, back_kb)
    await callback.answer()

@dp.callback_query(F.data == "top_categories")
async def show_top_categories(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    tz = await get_user_tz(user_id)
    now = datetime.now(tz)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    totals = await db.get_category_totals(user_id, start, now)
    text = format_top_categories(totals, "месяц")
    back_kb = create_keyboard([("⬅️ Назад", "stats_menu")], 1)
    await delete_previous_messages(user_id)
    await safe_edit_or_send(callback, text, back_kb)
    await callback.answer()

@dp.callback_query(F.data == "weekday_stats")
async def show_weekday_stats(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    tz = await get_user_tz(user_id)
    now = datetime.now(tz)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    totals = await db.get_weekday_totals(user_id, start, now)
    text = format_weekday_stats(totals)
    back_kb = create_keyboard([("⬅️ Назад", "stats_menu")], 1)
    await delete_previous_messages(user_id)
    await safe_edit_or_send(callback, text, back_kb)
    await callback.answer()

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

async def show_recurring_list(user_id: int, edit_callback: types.CallbackQuery = None):
    payments = await db.get_recurring_payments(user_id)
    if payments:
        lines = []
        for p in payments:
            lines.append(f"📌 <b>{p.name}</b> — {p.amount:.0f} ₽, {p.day_of_month}-го числа, категория: {p.category}")
        text = TEXTS["recurring_menu"] + "\n\n" + "\n".join(lines)
        kb = recurring_list_menu(payments)
    else:
        text = TEXTS["recurring_menu"] + "\n\n" + TEXTS["recurring_empty"]
        kb = recurring_empty_menu()

    if edit_callback:
        await safe_edit_or_send(edit_callback, text, kb)
    else:
        await safe_send_message(user_id, text, kb)

@dp.callback_query(F.data == "recurring_menu")
async def recurring_menu_handler(callback: types.CallbackQuery):
    await delete_previous_messages(callback.from_user.id)
    await show_recurring_list(callback.from_user.id, edit_callback=callback)
    await callback.answer()

@dp.callback_query(F.data == "add_recurring")
async def add_recurring_start(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await delete_previous_messages(user_id)
    user_recurring_state[user_id] = {"step": "name"}
    await safe_edit_or_send(callback, TEXTS["recurring_add_name"])
    await callback.answer()

@dp.callback_query(F.data.startswith("rcat:"))
async def recurring_category_chosen(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    category = callback.data.split(":", 1)[1]
    state = user_recurring_state.get(user_id, {})
    if state.get("step") != "category":
        await callback.answer()
        return
    state["category"] = category
    state["step"] = "day"
    await delete_previous_messages(user_id)
    await safe_edit_or_send(callback, TEXTS["recurring_add_day"])
    await callback.answer()

@dp.callback_query(F.data == "rcat_custom")
async def recurring_custom_category(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    state = user_recurring_state.get(user_id, {})
    if state.get("step") != "category":
        await callback.answer()
        return
    state["step"] = "category_custom"
    await delete_previous_messages(user_id)
    await safe_edit_or_send(callback, "✏️ Введите название категории для этого платежа:")
    await callback.answer()

@dp.callback_query(F.data.startswith("del_recurring:"))
async def delete_recurring_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    payment_id = int(callback.data.split(":")[1])
    payments = await db.get_recurring_payments(user_id)
    payment = next((p for p in payments if p.id == payment_id), None)
    name = payment.name if payment else "?"
    deleted = await db.delete_recurring_payment(payment_id, user_id)
    if deleted:
        await callback.answer(f"Платёж «{name}» удалён", show_alert=False)
    await delete_previous_messages(user_id)
    await show_recurring_list(user_id, edit_callback=callback)

async def recurring_payments_scheduler():
    while True:
        try:
            now_utc = datetime.utcnow()
            due = await db.get_due_recurring_payments(now_utc)
            for payment in due:
                try:
                    await db.add_expense(payment.user_id, payment.amount, payment.category)
                    await db.mark_recurring_triggered(payment.id, now_utc)
                    text = TEXTS["recurring_reminder"].format(
                        name=payment.name,
                        amount=payment.amount,
                        category=payment.category,
                    )
                    await safe_send_message(payment.user_id, text, main_menu())
                    logging.info(
                        f"Регулярный платёж #{payment.id} «{payment.name}» "
                        f"пользователя {payment.user_id} выполнен."
                    )
                except Exception as e:
                    logging.error(f"Ошибка выполнения регулярного платежа #{payment.id}: {e}")
        except Exception as e:
            logging.error(f"Ошибка в планировщике: {e}")

        await asyncio.sleep(3600)

@dp.message(F.text)
async def handle_all_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    tz = await get_user_tz(user_id)

    if user_id in user_recurring_state:
        state = user_recurring_state[user_id]
        step = state.get("step")

        if step == "name":
            if len(text) < 2:
                await safe_send_message(user_id, "❌ Слишком короткое название. Введите минимум 2 символа:")
                return
            if len(text) > 50:
                await safe_send_message(user_id, "❌ Слишком длинное название (макс. 50 символов):")
                return
            state["name"] = text
            state["step"] = "amount"
            await delete_previous_messages(user_id)
            await safe_send_message(user_id, TEXTS["recurring_add_amount"])
            return

        elif step == "amount":
            try:
                amount = float(text.replace(',', '.'))
                if amount <= 0:
                    raise ValueError
            except ValueError:
                await safe_send_message(user_id, "❌ Введите корректную сумму (число больше 0):")
                return
            state["amount"] = amount
            state["step"] = "category"
            await delete_previous_messages(user_id)
            await safe_send_message(user_id, TEXTS["recurring_add_category"], category_menu_for_recurring())
            return

        elif step == "category_custom":
            if len(text) < 2:
                await safe_send_message(user_id, TEXTS["category_too_short"])
                return
            if len(text) > 50:
                await safe_send_message(user_id, TEXTS["category_too_long"])
                return
            state["category"] = text
            state["step"] = "day"
            await delete_previous_messages(user_id)
            await safe_send_message(user_id, TEXTS["recurring_add_day"])
            return

        elif step == "day":
            try:
                day = int(text)
                if not 1 <= day <= 28:
                    raise ValueError
            except ValueError:
                await safe_send_message(user_id, TEXTS["recurring_invalid_day"])
                return
            name = state["name"]
            amount = state["amount"]
            category = state["category"]
            del user_recurring_state[user_id]
            await db.add_recurring_payment(user_id, name, amount, category, day)
            await delete_previous_messages(user_id)
            await safe_send_message(
                user_id,
                TEXTS["recurring_added"].format(name=name, amount=amount, category=category, day=day),
                main_menu()
            )
            return

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
            after_expense_menu(has_last=True)
        )
        return

    if user_id in user_date_state:
        await delete_previous_messages(user_id)
        try:
            date = parse_date_flexible(text, tz)
        except ValueError:
            await safe_send_message(user_id, TEXTS["invalid_date"])
            return
        day_start = date
        day_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        expenses = await db.get_expenses_by_date_range(user_id, day_start, day_end)
        result_text = format_expenses_for_date(expenses, date)
        del user_date_state[user_id]
        await safe_send_message(user_id, result_text, date_stats_result_menu(text))
        return

    if user_id in user_report_state:
        state = user_report_state[user_id]
        try:
            date = parse_date_flexible(text, tz)
            if state["step"] == "start":
                user_report_state[user_id] = {"step": "end", "start_date": date}
                await safe_send_message(user_id, TEXTS["enter_end_date"])
            else:
                start_date = state["start_date"]
                end_date = date
                if start_date > end_date:
                    await safe_send_message(user_id, TEXTS["date_range_error"])
                    return
                await delete_previous_messages(user_id)
                await safe_send_message(user_id, TEXTS["generating_report"])
                success = await generate_pdf_report(user_id, start_date=start_date, end_date=end_date)
                if not success:
                    await safe_send_message(user_id, TEXTS["no_data_report"])
                del user_report_state[user_id]
                await asyncio.sleep(1)
                await safe_send_message(user_id, TEXTS["main_menu"], main_menu())
        except ValueError:
            await safe_send_message(user_id, TEXTS["invalid_date"])
        return

    await delete_previous_messages(user_id)

    pure_number = re.match(r'^(\d+(?:[.,]\d{1,2})?)(?:\s*(?:р(?:уб)?|₽))?$', text)
    if pure_number:
        amount = float(pure_number.group(1).replace(',', '.'))
        if amount == 0:
            await safe_send_message(user_id, TEXTS["zero_amount"])
            return
        pending_expenses[user_id] = amount
        await safe_send_message(user_id, TEXTS["choose_category"], category_menu())
        return

    parsed = smart_parse_expense(text)
    if parsed:
        amount, category_hint = parsed
        pending_expenses[user_id] = amount

        if category_hint:
            matched_cat = None
            for cat in CATEGORIES:
                if cat.lower() in category_hint.lower() or category_hint.lower() in cat.lower():
                    matched_cat = cat
                    break

            if matched_cat:
                amount = pending_expenses.pop(user_id)
                await db.add_expense(user_id, amount, matched_cat)
                user_last_expense[user_id] = {"amount": amount, "category": matched_cat}
                await safe_send_message(
                    user_id,
                    f"✅ Добавлено: <b>{amount:.2f} ₽</b> → «{matched_cat}»\n"
                    f"(распознано из: «{text}»)",
                    after_expense_menu(has_last=True)
                )
            else:
                hint_text = (
                    f"💰 Сумма: <b>{amount:.2f} ₽</b>\n"
                    f"💡 Возможная категория: «{category_hint}»\n\n"
                    f"Выберите категорию или нажмите на подсказку:"
                )

                builder = InlineKeyboardBuilder()
                builder.button(text=f'✅ «{category_hint[:25]}»', callback_data=f"hint_cat:{category_hint[:50]}")
                for cat in CATEGORIES:
                    builder.button(text=cat, callback_data=f"cat:{cat}")
                builder.button(text="✏️ Своя категория", callback_data="custom_category")
                builder.adjust(1, 2, 2, 1)
                await safe_send_message(user_id, hint_text, builder.as_markup())
        else:
            hint_text = f"💰 Сумма: <b>{amount:.2f} ₽</b>\n\nВыберите категорию:"
            await safe_send_message(user_id, hint_text, category_menu())
    else:
        await safe_send_message(
            user_id,
            "💰 Выберите сумму или введите число:",
            quick_amount_menu()
        )

@dp.error()
async def error_handler(exception: Exception):
    logging.error(f"Ошибка в обработчике: {exception}", exc_info=True)
    return True

async def main():
    await db.init_db()
    logging.info("Бот запущен!")
    asyncio.create_task(recurring_payments_scheduler())
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
