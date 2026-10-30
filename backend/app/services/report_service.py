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


def _format_interval(values: Any) -> str:
    if values is None:
        return 'Not provided'
    try:
        lower, upper = values
    except (TypeError, ValueError):
        return 'Invalid interval'
    lower_value = _to_float(lower)
    upper_value = _to_float(upper)
    if lower_value is None or upper_value is None:
        return 'Invalid interval'
    if lower_value > upper_value:
        return 'Invalid interval'
    return f'{lower_value:.1f} to {upper_value:.1f} years'


def _get_output_field(assessment: dict[str, Any], *keys: str) -> Any:
    output = assessment.get('output_payload') or {}
    for key in keys:
        if key in output:
            return output.get(key)
    return assessment.get(key)


def generate_assessment_report_pdf(assessment: dict[str, Any]) -> bytes:
    if not isinstance(assessment, dict):
        raise ValueError('Assessment data is required to generate a PDF report.')

    status = assessment.get('status')
    if status != 'completed':
        raise ValueError('Report generation is only supported for completed assessments.')

    output = assessment.get('output_payload') or {}
    chronological_age = assessment.get('chronological_age')
    predicted_brain_age = output.get('predicted_brain_age')
    brain_age_difference = output.get('brain_age_difference')
    uncertainty_interval = output.get('uncertainty_interval')

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
        ['Uncertainty interval', _format_interval(uncertainty_interval)],
        ['Model name', str(output.get('model_name') or assessment.get('model_name') or 'Not available')],
        ['Model version', str(output.get('model_version') or assessment.get('model_version') or 'Not available')],
        ['Evaluation dataset', str(output.get('evaluation_dataset') or output.get('dataset_evaluated') or 'Not available')],
        ['Last evaluated', str(output.get('last_evaluated') or 'Not available')],
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
    story.append(Paragraph('Clinical and scientific safeguards', heading_style))
    story.append(Paragraph(
        'This report does not constitute a diagnostic certificate, treatment recommendation, or medical claim. '
        'No unsupported clinical treatment advice is included.',
        body_style,
    ))
    story.append(Paragraph(
        'Research use only: this output is intended to support scientific review and exploratory analysis, not diagnosis or therapeutic decision-making.',
        body_style,
    ))
    story.append(Spacer(1, 18))

    if 'mri_preview' in output or 'mri_preview_url' in output:
        story.append(Paragraph('MRI visualization', heading_style))
        story.append(Paragraph('MRI preview information is available in the assessment metadata.', body_style))
    else:
        story.append(Paragraph('MRI visualization', heading_style))
        story.append(Paragraph('No approved MRI preview or visualization was supplied for this assessment.', body_style))

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
