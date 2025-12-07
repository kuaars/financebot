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

def register_chicoree_font():
    try:
        font_paths = [
            "Chicoree.ttf",
            "fonts/Chicoree.ttf",
            "C:/Windows/Fonts/Chicoree.ttf",
            "/usr/share/fonts/Chicoree.ttf",
            "/Library/Fonts/Chicoree.ttf",
        ]

        for font_path in font_paths:
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('Chicoree', font_path))
                return True
        return False
    except Exception:
        return False

def generate_expense_report(user_id: int, expenses, start_date: datetime, end_date: datetime, username: str = ""):
    has_chicoree = register_chicoree_font()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{user_id}_{timestamp}.pdf"

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm
    )

    styles = getSampleStyleSheet()

    font_name = 'Chicoree' if has_chicoree else 'Helvetica'

    title_style = ParagraphStyle(
        'Title',
        parent=styles['Title'],
        fontName=font_name,
        fontSize=20,
        alignment=TA_CENTER,
        textColor=colors.darkblue,
        spaceAfter=15
    )

    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=12,
        alignment=TA_CENTER,
        textColor=colors.darkblue,
        spaceAfter=8
    )

    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        alignment=TA_LEFT,
        leading=12
    )

    bold_style = ParagraphStyle(
        'Bold',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        alignment=TA_LEFT,
        leading=12,
        textColor=colors.darkred
    )

    amount_style = ParagraphStyle(
        'Amount',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        alignment=TA_RIGHT,
        leading=12
    )

    story = []

    story.append(Paragraph("ФИНАНСОВЫЙ ОТЧЕТ", title_style))
    story.append(Spacer(1, 10 * mm))

    report_info = [
        f"<b>Дата формирования:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        f"<b>Пользователь:</b> {username if username else f'ID {user_id}'}",
        f"<b>Период:</b> с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')}"
    ]

    for info in report_info:
        story.append(Paragraph(info, normal_style))

    story.append(Spacer(1, 15 * mm))

    total = sum(exp.amount for exp in expenses)

    story.append(Paragraph("<b>СВОДНАЯ ИНФОРМАЦИЯ</b>", header_style))
    story.append(Spacer(1, 8 * mm))

    summary_data = [
        ["Количество операций:", f"{len(expenses)}"],
        ["Общая сумма расходов:", f"{total:.2f} ₽"],
    ]

    category_totals = {}
    for exp in expenses:
        category_totals[exp.category] = category_totals.get(exp.category, 0) + exp.amount

    if category_totals:
        story.append(Paragraph("<b>РАСХОДЫ ПО КАТЕГОРИЯМ:</b>", normal_style))
        for category, amount in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
            summary_data.append([f"  {category}:", f"{amount:.2f} ₽"])

    summary_table_data = []
    for label, value in summary_data:
        summary_table_data.append([
            Paragraph(label, normal_style),
            Paragraph(value, amount_style)
        ])

    summary_table = Table(summary_table_data, colWidths=[120 * mm, 50 * mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 1), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))

    story.append(summary_table)
    story.append(Spacer(1, 15 * mm))

    if expenses:
        story.append(Paragraph("<b>ДЕТАЛИЗАЦИЯ ОПЕРАЦИЙ</b>", header_style))
        story.append(Spacer(1, 8 * mm))

        table_data = [[
            Paragraph("<b>Дата и время</b>", bold_style),
            Paragraph("<b>Категория</b>", bold_style),
            Paragraph("<b>Сумма (₽)</b>", bold_style)
        ]]

        for exp in expenses:
            date_str = exp.date.strftime("%d.%m.%Y %H:%M")
            table_data.append([
                Paragraph(date_str, normal_style),
                Paragraph(exp.category, normal_style),
                Paragraph(f"{exp.amount:.2f}", amount_style)
            ])

        table_data.append([
            Paragraph("<b>ИТОГО:</b>", bold_style),
            Paragraph("", normal_style),
            Paragraph(f"<b>{total:.2f}</b>", bold_style)
        ])

        operations_table = Table(table_data, colWidths=[70 * mm, 60 * mm, 40 * mm])

        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#007fff")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),

            ('BACKGROUND', (0, 1), (-1, -2), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -2), colors.black),
            ('FONTSIZE', (0, 1), (-1, -2), 10),
            ('BOTTOMPADDING', (0, 1), (-1, -2), 6),
            ('TOPPADDING', (0, 1), (-1, -2), 6),

            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#e6f2ff")),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),
            ('FONTSIZE', (0, -1), (-1, -1), 11),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
            ('TOPPADDING', (0, -1), (-1, -1), 8),

            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#007fff")),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor("#007fff")),
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.HexColor("#007fff")),

            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
        ])

        operations_table.setStyle(table_style)
        story.append(operations_table)

    story.append(Spacer(1, 15 * mm))
    story.append(Paragraph("--- Конец отчета ---", header_style))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(f"Сформировано @FinanceBot", normal_style))

    doc.build(story)

    return filename

def generate_expense_report_simple(user_id: int, expenses, start_date: datetime, end_date: datetime,
                                   username: str = ""):
    has_chicoree = register_chicoree_font()
    font_name = 'Chicoree' if has_chicoree else 'Helvetica'

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{user_id}_{timestamp}.pdf"

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm
    )

    story = []

    title_data = [["ФИНАНСОВЫЙ ОТЧЕТ"]]
    title_table = Table(title_data, colWidths=[180 * mm])
    title_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (0, 0), font_name),
        ('FONTSIZE', (0, 0), (0, 0), 18),
        ('TEXTCOLOR', (0, 0), (0, 0), colors.darkblue),
        ('BOTTOMPADDING', (0, 0), (0, 0), 15),
    ]))
    story.append(title_table)

    info_data = [
        ["Дата формирования:", datetime.now().strftime("%d.%m.%Y %H:%M")],
        ["Пользователь:", username if username else f"ID {user_id}"],
        ["Период:", f"с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')}"],
    ]

    info_table = Table(info_data, colWidths=[60 * mm, 120 * mm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 15 * mm))

    total = sum(exp.amount for exp in expenses)
    stats_data = [
        ["СТАТИСТИКА", ""],
        ["Количество операций:", str(len(expenses))],
        ["Общая сумма:", f"{total:.2f} ₽"],
    ]

    stats_table = Table(stats_data, colWidths=[100 * mm, 80 * mm])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('FONTNAME', (0, 0), (-1, 0), font_name),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('FONTNAME', (0, 1), (-1, -1), font_name),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 15 * mm))

    if expenses:
        details_title = [["ДЕТАЛИ ОПЕРАЦИЙ"]]
        details_title_table = Table(details_title, colWidths=[180 * mm])
        details_title_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#007fff")),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
            ('FONTNAME', (0, 0), (0, 0), font_name),
            ('FONTSIZE', (0, 0), (0, 0), 12),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (0, 0), 8),
            ('TOPPADDING', (0, 0), (0, 0), 8),
        ]))
        story.append(details_title_table)
        story.append(Spacer(1, 5 * mm))

        headers = [["Дата", "Категория", "Сумма"]]
        headers_table = Table(headers, colWidths=[80 * mm, 60 * mm, 40 * mm])
        headers_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#007fff")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
        ]))
        story.append(headers_table)

        operations_data = []
        for exp in expenses:
            date_str = exp.date.strftime("%d.%m.%Y %H:%M")
            operations_data.append([date_str, exp.category, f"{exp.amount:.2f}"])

        operations_data.append(["ИТОГО:", "", f"{total:.2f}"])

        operations_table = Table(operations_data, colWidths=[80 * mm, 60 * mm, 40 * mm])
        operations_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -2), font_name),
            ('FONTSIZE', (0, 0), (-1, -2), 10),
            ('ALIGN', (2, 0), (2, -2), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -2), 6),
            ('TOPPADDING', (0, 0), (-1, -2), 6),

            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#e6f2ff")),
            ('FONTNAME', (0, -1), (-1, -1), font_name),
            ('FONTSIZE', (0, -1), (-1, -1), 11),
            ('ALIGN', (2, -1), (2, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
            ('TOPPADDING', (0, -1), (-1, -1), 8),

            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor("#007fff")),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, colors.HexColor("#007fff")),
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.HexColor("#007fff")),
        ]))
        story.append(operations_table)

    story.append(Spacer(1, 15 * mm))
    footer_data = [["--- Конец отчета ---"]]
    footer_table = Table(footer_data, colWidths=[180 * mm])
    footer_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (0, 0), font_name),
        ('FONTSIZE', (0, 0), (0, 0), 10),
        ('TEXTCOLOR', (0, 0), (0, 0), colors.grey),
    ]))
    story.append(footer_table)

    doc.build(story)

    return filename