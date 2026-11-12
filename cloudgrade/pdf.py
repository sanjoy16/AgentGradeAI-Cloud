from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted


def build_pdf(item, report):
    output = BytesIO()
    styles = getSampleStyleSheet()
    story = []
    def p(text, style='BodyText'):
        story.append(Paragraph(escape(str(text)).replace('\n', '<br/>'), styles[style]))
        story.append(Spacer(1, 7))
    p('AgentGradeAI-Cloud', 'Title')
    p('Faculty-approved programming assessment', 'Heading2')
    for label, value in [('Student', item.student.name), ('Student ID', item.student.student_id),
                         ('Assignment', item.title), ('Submission', item.id), ('Source SHA-256', item.source_hash),
                         ('Approved', item.approved_at), ('Final score', f"{report['score']:.2f} / 100")]:
        p(f'{label}: {value}')
    p(report['summary'])
    rows = [['Evaluation agent', 'Awarded', 'Maximum', 'Status']]
    rows += [[a['name'], str(a['score']) if a['score'] is not None else 'Unassessed', str(a['maximum']), a['status']] for a in report['agents']]
    table = Table(rows, colWidths=[2.5*inch, .8*inch, .8*inch, 1.3*inch], repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#123b4a')),
                              ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTSIZE', (0, 0), (-1, -1), 8),
                              ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                              ('BOTTOMPADDING', (0, 0), (-1, -1), 9)]))
    story.append(table)
    p('Faculty feedback', 'Heading2')
    p(report.get('faculty_feedback', ''))
    p('AI commentary', 'Heading2')
    p(report.get('ai_feedback', ''))
    for a in report['agents']:
        p(a['name'], 'Heading2')
        for label in ('methodology', 'findings', 'recommendation'):
            p(f'{label.title()}: {a[label]}')
        if a.get('ai_review'):
            p('Independent AI review: ' + a['ai_review'])
        if a.get('override_reason'):
            p('Faculty adjustment: ' + a['override_reason'])
        # Complete bounded tool evidence includes runtime diagnostics and hidden tests.
        # Only approved reports reach students; faculty is warned about test disclosure.
        import json
        raw = json.dumps(a.get('evidence', {}), ensure_ascii=True, indent=2)
        if raw != '{}':
            p('Tool evidence', 'Heading3')
            lines = [line[i:i+95] for line in raw.splitlines() for i in range(0, max(1, len(line)), 95)]
            story.append(Preformatted('\n'.join(lines), styles['Code'], maxLineLength=95))
    def page(canvas, doc):
        canvas.setFont('Helvetica', 8)
        canvas.drawString(40, 25, 'AgentGradeAI-Cloud | Confidential student assessment')
        canvas.drawRightString(555, 25, f'Page {doc.page}')
    SimpleDocTemplate(output, title='AgentGradeAI assessment', topMargin=40, bottomMargin=45).build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()
