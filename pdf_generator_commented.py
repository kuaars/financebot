import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import platform


def register_custom_fonts():
    """Регистрирует шрифты с поддержкой кириллицы"""
    try:
        # Сначала попробуем зарегистрировать стандартные шрифты с кириллицей
        system = platform.system()

        if system == "Windows":
            # Шрифты Windows
            font_paths = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/times.ttf",
                "C:/Windows/Fonts/calibri.ttf",
            ]
        elif system == "Linux":
            # Шрифты Linux
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
            ]
        elif system == "Darwin":  # macOS
            # Шрифты macOS
            font_paths = [
                "/Library/Fonts/Arial.ttf",
                "/Library/Fonts/Times New Roman.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        else:
            font_paths = []

        # Добавляем общие пути
        font_paths.extend([
            "arial.ttf",
            "times.ttf",
            "fonts/arial.ttf",
            "fonts/times.ttf",
        ])

        # Регистрируем Arial как основной шрифт
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    if font_path.endswith('.ttf'):
                        pdfmetrics.registerFont(TTFont('Arial', font_path))
                        pdfmetrics.registerFont(TTFont('Arial-Bold', font_path))
                    elif font_path.endswith('.ttc'):
                        # Обработка коллекций шрифтов
                        pdfmetrics.registerFont(TTFont('Arial', font_path, subfontIndex=0))
                    print(f"Шрифт зарегистрирован: {font_path}")
                    return True
                except Exception as e:
                    print(f"Ошибка регистрации шрифта {font_path}: {e}")
                    continue

        # Если не нашли подходящий шрифт, используем встроенный Helvetica
        print("Используется стандартный шрифт Helvetica (ограниченная поддержка кириллицы)")
        return False

    except Exception as e:
        print(f"Ошибка при регистрации шрифтов: {e}")
        return False


def generate_expense_report(user_id: int, expenses, start_date: datetime, end_date: datetime, username: str = ""):
    """Генерирует PDF отчет о расходах"""

    # Регистрируем шрифты
    has_custom_font = register_custom_fonts()

    # Выбираем шрифт
    if has_custom_font:
        font_name = 'Arial'
        bold_font_name = 'Arial-Bold'
    else:
        font_name = 'Helvetica'
        bold_font_name = 'Helvetica-Bold'

    # Создаем имя файла
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{user_id}_{timestamp}.pdf"

    # Настройки документа
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm
    )

    # Создаем стили
    styles = getSampleStyleSheet()

    # Основные стили
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontName=bold_font_name,
        fontSize=16,
        alignment=TA_CENTER,
        textColor=colors.darkblue,
        spaceAfter=10 * mm
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        alignment=TA_LEFT,
        leading=12
    )

    bold_style = ParagraphStyle(
        'CustomBold',
        parent=styles['Normal'],
        fontName=bold_font_name,
        fontSize=10,
        alignment=TA_LEFT,
        leading=12,
        textColor=colors.black
    )

    center_style = ParagraphStyle(
        'CustomCenter',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        alignment=TA_CENTER,
        leading=12
    )

    right_style = ParagraphStyle(
        'CustomRight',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        alignment=TA_RIGHT,
        leading=12
    )

    # Собираем документ
    story = []

    # Заголовок
    story.append(Paragraph("ФИНАНСОВЫЙ ОТЧЕТ", title_style))

    # Информация об отчете
    story.append(Paragraph(f"<b>Дата формирования:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}", normal_style))
    story.append(Paragraph(f"<b>Пользователь:</b> {username if username else f'ID {user_id}'}", normal_style))
    story.append(Paragraph(f"<b>Период:</b> с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')}",
                           normal_style))

    story.append(Spacer(1, 10 * mm))

    # Общая статистика
    if expenses:
        total = sum(exp.amount for exp in expenses)

        # Сводная таблица
        summary_data = [
            [Paragraph("<b>Параметр</b>", bold_style), Paragraph("<b>Значение</b>", bold_style)],
            ["Количество операций:", str(len(expenses))],
            ["Общая сумма расходов:", f"{total:.2f} ₽"],
        ]

        # Добавляем расходы по категориям
        category_totals = {}
        for exp in expenses:
            category_totals[exp.category] = category_totals.get(exp.category, 0) + exp.amount

        if category_totals:
            summary_data.append(["", ""])
            summary_data.append([Paragraph("<b>Расходы по категориям:</b>", bold_style), ""])

            for category, amount in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
                summary_data.append([f"  {category}", f"{amount:.2f} ₽"])

        # Создаем таблицу
        summary_table = Table(summary_data, colWidths=[100 * mm, 70 * mm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4F81BD")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), bold_font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),

            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))

        story.append(summary_table)
        story.append(Spacer(1, 15 * mm))

        # Детали операций
        story.append(Paragraph("<b>ДЕТАЛИЗАЦИЯ ОПЕРАЦИЙ</b>", bold_style))
        story.append(Spacer(1, 5 * mm))

        # Таблица операций
        operations_data = [
            [
                Paragraph("<b>Дата</b>", bold_style),
                Paragraph("<b>Время</b>", bold_style),
                Paragraph("<b>Категория</b>", bold_style),
                Paragraph("<b>Сумма (₽)</b>", bold_style)
            ]
        ]

        for exp in expenses:
            operations_data.append([
                exp.date.strftime("%d.%m.%Y"),
                exp.date.strftime("%H:%M"),
                exp.category,
                f"{exp.amount:.2f}"
            ])

        # Итоговая строка
        operations_data.append([
            Paragraph("<b>ИТОГО:</b>", bold_style),
            "",
            "",
            Paragraph(f"<b>{total:.2f} ₽</b>", bold_style)
        ])

        operations_table = Table(operations_data, colWidths=[40 * mm, 30 * mm, 60 * mm, 40 * mm])
        operations_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4F81BD")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), bold_font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),

            ('FONTNAME', (0, 1), (-1, -2), font_name),
            ('FONTSIZE', (0, 1), (-1, -2), 10),
            ('ALIGN', (0, 1), (-1, -2), 'CENTER'),
            ('ALIGN', (3, 1), (3, -2), 'RIGHT'),
            ('VALIGN', (0, 1), (-1, -2), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 1), (-1, -2), 6),
            ('TOPPADDING', (0, 1), (-1, -2), 6),

            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#D9E1F2")),
            ('FONTNAME', (0, -1), (-1, -1), bold_font_name),
            ('FONTSIZE', (0, -1), (-1, -1), 11),
            ('ALIGN', (3, -1), (3, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
            ('TOPPADDING', (0, -1), (-1, -1), 8),

            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#4F81BD")),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor("#4F81BD")),
        ]))

        story.append(operations_table)
    else:
        # Нет данных
        story.append(Paragraph("<b>Нет данных за выбранный период</b>", bold_style))
        story.append(Paragraph("За указанный период расходы не найдены.", normal_style))

    story.append(Spacer(1, 10 * mm))

    # Подвал
    story.append(Paragraph("_" * 50, center_style))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Сформировано FinanceBot", center_style))

    # Генерируем PDF
    doc.build(story)

    return filename
