from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return None
    return float_value if math.isfinite(float_value) else None


def _format_yrs(value: Any) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return 'Not available'
    return f'{numeric:.1f} years'


def _get_output_field(assessment: dict[str, Any], *keys: str) -> Any:
    output = assessment.get('output_payload') or {}
    for key in keys:
        if key in output:
            return output.get(key)
    return assessment.get(key)


def _nutrition_tips(difference: float | None) -> tuple[tuple[str, str], tuple[str, str]]:
    vegetarian_label = 'Nutrition plan (vegetarian)'
    non_vegetarian_label = 'Nutrition plan (non-vegetarian)'
    if difference is None:
        return (
            (vegetarian_label, 'Meal ideas: breakfast, oats with fruit and nuts; lunch, lentils with whole grains and vegetables; dinner, tofu with vegetables.'),
            (non_vegetarian_label, 'Meal ideas: breakfast, eggs with whole-grain toast and fruit; lunch, fish or chicken with whole grains and vegetables; dinner, beans with vegetables.'),
        )
    if difference <= -5:
        return (
            (vegetarian_label, 'Variety plan: breakfast, yogurt or fortified soy yogurt with oats and fruit; lunch, lentils, leafy greens, and brown rice; dinner, tofu with mixed vegetables and whole grains.'),
            (non_vegetarian_label, 'Variety plan: breakfast, eggs with whole-grain toast and fruit; lunch, fish with leafy greens and brown rice; dinner, bean soup with vegetables, or lean chicken with whole grains.'),
        )
    if difference <= 0:
        return (
            (vegetarian_label, 'Regular-meal plan: breakfast, oatmeal with milk or fortified soy drink and fruit; lunch, chickpea and vegetable bowl with whole grains; dinner, paneer or tofu with vegetables and roti.'),
            (non_vegetarian_label, 'Regular-meal plan: breakfast, eggs with whole-grain toast and fruit; lunch, chicken with vegetables and whole grains; dinner, lentil soup with vegetables, or fish with roti.'),
        )
    if difference <= 5:
        return (
            (vegetarian_label, 'Fiber-at-meals plan: breakfast, fruit with oats and yogurt or fortified soy yogurt; lunch, rajma or beans with brown rice and vegetables; dinner, tofu with vegetables and whole-grain roti.'),
            (non_vegetarian_label, 'Fiber-at-meals plan: breakfast, eggs with oats or whole-grain toast and fruit; lunch, fish or chicken with beans, vegetables, and brown rice; dinner, vegetable dal with an egg if desired.'),
        )
    if difference <= 10:
        return (
            (vegetarian_label, 'Meal-prep plan: breakfast, overnight oats with fruit and seeds; lunch, lentil and vegetable grain bowl; dinner, tofu or chickpeas with vegetables and whole grains.'),
            (non_vegetarian_label, 'Meal-prep plan: breakfast, boiled eggs with fruit and whole-grain toast; lunch, prepared fish or chicken with vegetables and whole grains; dinner, bean and vegetable soup with an egg if desired.'),
        )
    return (
        (vegetarian_label, 'Gradual plate-building plan: breakfast, add fruit to oats or whole-grain toast; lunch, add a serving of lentils or beans and vegetables to a grain bowl; dinner, add tofu with vegetables and rice or roti.'),
        (non_vegetarian_label, 'Gradual plate-building plan: breakfast, eggs with fruit and whole-grain toast; lunch, add chicken or fish plus vegetables to rice or roti; dinner, include beans or lentils with vegetables, with egg or lean poultry if desired.'),
    )


def _health_tips(brain_age_difference: Any) -> tuple[str, list[tuple[str, str]]]:
    difference = _to_float(brain_age_difference)
    nutrition_tips = _nutrition_tips(difference)
    if difference is None:
        return 'General wellness', [
            ('Screen time', 'Take regular screen breaks and reduce device use before bedtime.'),
            ('Sleep cycle', 'Keep a consistent sleep and wake schedule and allow 7-9 hours for sleep.'),
            *nutrition_tips,
            ('Exercise', 'Build toward at least 150 minutes of moderate activity each week, plus strength activity on 2 days.'),
            ('Meditation', 'Start with at least 5 minutes of quiet breathing or mindfulness each day.'),
        ]

    if difference <= -5:
        return 'Lower estimate (difference at or below -5 years)', [
            ('Screen time', 'Keep regular eye and movement breaks during long screen sessions and avoid screens during the last hour before bed.'),
            ('Sleep cycle', 'Maintain your current healthy routine with a consistent sleep and wake time and 7-9 hours nightly.'),
            *nutrition_tips,
            ('Exercise', 'Continue regular activity and aim for at least 150 minutes of moderate exercise weekly, with strength activity on 2 days.'),
            ('Meditation', 'Maintain a daily mindfulness or breathing routine for at least 5 minutes.'),
        ]
    if difference <= 0:
        return 'Maintenance (difference at or below 0 years)', [
            ('Screen time', 'Take a short movement or eye break during long screen sessions and keep the last 30 minutes before bed screen-free.'),
            ('Sleep cycle', 'Maintain a regular sleep and wake time and aim for 7-9 hours nightly.'),
            *nutrition_tips,
            ('Exercise', 'Maintain regular activity; aim for at least 150 minutes of moderate exercise weekly and strength activity on 2 days.'),
            ('Meditation', 'Practice for at least 5 minutes daily, or continue a routine that works for you.'),
        ]
    if difference <= 5:
        return 'Foundational habits (difference over 0 to 5 years)', [
            ('Screen time', 'Take a brief break every 30–60 minutes and make the last hour before bed screen-light.'),
            ('Sleep cycle', 'Set a steady bedtime and wake time, and protect a 7-9-hour sleep opportunity each night.'),
            *nutrition_tips,
            ('Exercise', 'Schedule regular walks or similar moderate activity and work toward 150 minutes weekly, with strength activity on 2 days.'),
            ('Meditation', 'Set aside at least 5 minutes daily for breathing or mindfulness.'),
        ]
    if difference <= 10:
        return 'Focused routine (difference over 5 to 10 years)', [
            ('Screen time', 'Plan screen-free breaks during the day and stop recreational screen use about 1 hour before bed.'),
            ('Sleep cycle', 'Keep wake time consistent, wind down before bed, and allow 7-9 hours for sleep each night.'),
            *nutrition_tips,
            ('Exercise', 'Put moderate activity on the calendar across the week; gradually work toward 150 minutes weekly and strength activity on 2 days.'),
            ('Meditation', 'Aim for at least 10 minutes daily of mindfulness, meditation, or slow breathing.'),
        ]
    return 'Structured routine (difference over 10 years)', [
        ('Screen time', 'Add planned screen-free blocks, take movement breaks, and keep devices out of the bedroom during the hour before sleep.'),
        ('Sleep cycle', 'Choose a consistent wake time, follow a calming wind-down routine, and reserve 7-9 hours for sleep nightly.'),
        *nutrition_tips,
        ('Exercise', 'If currently inactive, begin with manageable 10-minute walks and build gradually toward 150 minutes of moderate activity weekly plus strength activity on 2 days.'),
        ('Meditation', 'Build toward at least 15 minutes daily of mindfulness or slow breathing, starting shorter if needed.'),
    ]


def generate_assessment_report_pdf(assessment: dict[str, Any]) -> bytes:
    if not isinstance(assessment, dict):
        raise ValueError('Assessment data is required to generate a PDF report.')

    status = assessment.get('status')
    if status != 'completed':
        raise ValueError('Report generation is only supported for completed assessments.')

    output = assessment.get('output_payload') or {}
    chronological_age = _get_output_field(assessment, 'chronological_age')
    predicted_brain_age = _get_output_field(assessment, 'predicted_brain_age')
    brain_age_difference = _get_output_field(assessment, 'brain_age_difference')
    predicted_value = _to_float(predicted_brain_age)
    chronological_value = _to_float(chronological_age)
    if predicted_value is not None and chronological_value is not None:
        brain_age_difference = predicted_value - chronological_value

    if predicted_brain_age is None and chronological_age is None and 'model_name' not in output:
        raise ValueError('The assessment does not contain result data suitable for a report.')

    generated_at = assessment.get('updated_at') or assessment.get('created_at') or datetime.now(timezone.utc).isoformat()
    if isinstance(generated_at, datetime):
        generated_at_iso = generated_at.astimezone(timezone.utc).isoformat()
    else:
        generated_at_iso = str(generated_at)

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        spaceAfter=12,
        textColor=colors.HexColor('#173E6B'),
    )
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        spaceAfter=8,
        textColor=colors.HexColor('#173E6B'),
    )
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        spaceAfter=6,
    )
    small_style = ParagraphStyle(
        'SmallText',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#4B5563'),
    )

    story: list[Any] = []
    story.append(Paragraph('NeuroAge Brain Age Report', title_style))
    if assessment.get('subject_name'):
        story.append(Paragraph(f"Assessment name: {escape(str(assessment['subject_name']))}", body_style))
    story.append(Paragraph(f'Generated: {escape(generated_at_iso)}', body_style))
    story.append(Spacer(1, 12))

    table_data = [
        ['Field', 'Value'],
        ['Assessment name', str(assessment.get('subject_name') or 'Not provided')],
        ['Chronological age', _format_yrs(chronological_age)],
        ['Predicted brain age', _format_yrs(predicted_brain_age)],
        ['Brain age difference', _format_yrs(brain_age_difference)],
        ['Model name', str(output.get('model_name') or assessment.get('model_name') or 'Not available')],
        ['Model version', str(output.get('model_version') or assessment.get('model_version') or 'Not available')],
    ]
    report_table = Table(table_data, colWidths=[220, 200])
    report_table.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E5EEF8')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ])
    )
    story.append(report_table)
    story.append(Spacer(1, 18))

    story.append(Paragraph('Result summary', heading_style))
    explanation = (
        'This report summarizes the model estimate for the MRI assessment. It provides an exploratory estimate of brain age '
        'and should be interpreted as research-oriented output rather than a medical diagnosis.'
    )
    story.append(Paragraph(explanation, body_style))

    limitations = output.get('model_limitations') or ['This estimate is exploratory and not a medical diagnosis.']
    if isinstance(limitations, str):
        limitations = [limitations]
    story.append(Paragraph('Key limitations', heading_style))
    for item in limitations:
        story.append(Paragraph(f'• {escape(str(item))}', body_style))

    story.append(Spacer(1, 12))
    story.append(Paragraph('Health tips', heading_style))
    tip_level, tips = _health_tips(brain_age_difference)
    difference_text = _format_yrs(brain_age_difference)
    story.append(Paragraph(
        f'Personalization level: {escape(tip_level)}. Brain-age difference used: {escape(difference_text)}.',
        body_style,
    ))
    story.append(Paragraph(
        'These general wellness ideas and meal examples are educational, not medical advice. The brain-age difference is a model estimate and does not determine nutritional needs. Adapt meal ideas for allergies, dietary needs, and clinician advice.',
        small_style,
    ))
    for label, recommendation in tips:
        story.append(Paragraph(f'<b>{escape(label)}:</b> {escape(recommendation)}', body_style))

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 9)
        canvas.setFillColor(colors.HexColor('#4B5563'))
        canvas.drawRightString(letter[0] - 54, 28, f'Page {doc.page}')
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=42,
        bottomMargin=54,
        title='NeuroAge Brain Age Report',
        author='NeuroAge API',
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()
