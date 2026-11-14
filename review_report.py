"""Decision-focused presentation of recorded evidence; never executes tools or changes marks."""
from io import BytesIO
import hashlib
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from student_report import FONT, BOLD, deductions
from detailed_report import proposed_tests, recorded_inputs


def brief(value, limit=700):
    text = ' '.join(str(value or '').split())
    return text if len(text) <= limit else text[:limit].rstrip() + ' [excerpt; full evidence in application]'


def agent_rows(result):
    return [{'Agent': a['name'], 'Status': a['status'],
             'Finding / scope': brief(a.get('result') or 'No result retained.', 450),
             'Evidence': ', '.join(a.get('evidence_ids', [])) or 'None'}
            for a in result.get('agent_details', [])]


def render_review_pdf(name, roll, title, result):
    if result.get('approval_status') != 'approved':
        raise PermissionError('Faculty approval is required for PDF release.')
    out = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Body', fontName=FONT, fontSize=9, leading=13, spaceAfter=6, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='Heading', fontName=BOLD, fontSize=13, leading=17, spaceBefore=10, spaceAfter=6, keepWithNext=True, textColor=colors.HexColor('#183a59')))
    styles.add(ParagraphStyle(name='CellText', parent=styles['Body'], fontSize=8, leading=11, spaceAfter=0))
    def p(value, cell=False):
        return Paragraph(escape(str(value)), styles['CellText' if cell else 'Body'])
    story = []
    def heading(value): story.append(Paragraph(escape(value), styles['Heading']))
    def table(rows, widths):
        grid = [[p(value, True) for value in row] for row in rows]
        t = Table(grid, colWidths=widths, repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf0f7')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),0.5,colors.HexColor('#9aaabd')),
            ('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),
            ('LINEBELOW',(0,1),(-1,-1),0.25,colors.HexColor('#d8e1ea'))]))
        story.extend([t, Spacer(1,8)])
    heading('GradeAI C assignment assessment report')
    story.extend([p(brief(title,240)),p('Student: '+brief(name,100)+' | Roll: '+brief(roll,60)),
        p('Approved: '+str(result.get('approved_at','Recorded approval')))])
    approved = result.get('approved_score',result.get('score',0))
    provisional = result.get('provisional_score',result.get('score',0))
    heading(f'Final score: {approved}/100')
    story.append(p(f'Provisional rubric: {provisional}/100 | Faculty adjustment: {approved-provisional:+}'))
    story.append(p('Profile: '+str(result.get('assignment_profile','Not retained'))))
    story.append(p(brief(result.get('assessment_mode','Checked scope not retained.'),1200)))
    if result.get('review_required'):
        story.append(p('Review flag recorded: incomplete checks or findings require interpretation within the checked scope. Faculty approval does not turn incomplete checks into passes.'))
    heading('Rubric breakdown')
    table([['Criterion','Status / basis','Points']] + [[r['criterion'],brief(r.get('status','')+' - '+r.get('analysis',''),350),f"{r['score']}/{r['max']}"] for r in result.get('rubric',[])],[135,306,70])
    heading('Faculty feedback')
    story.append(p(brief(result.get('faculty_note') or 'No additional faculty comments.',1800)))
    heading('Feedback: where and how to improve')
    issues = deductions(result)
    if not issues: story.append(p('No rubric deductions were recorded. This does not establish correctness outside the checked scope.'))
    for issue in issues:
        heading(f"{issue['criterion']}: {issue['lost']} points {issue['kind'].lower()}")
        for label,key in [('Program portion','where'),('Why','reason'),('How to revise','action'),('Evidence','evidence')]:
            story.append(p(label+': '+brief(issue.get(key,''),1000)))
    story.append(p('Held points are unverified credit, not a proven wrong answer. Heuristic deductions require faculty judgement.'))
    for correction in result.get('report_corrections',[]): story.append(p('Evidence interpretation: '+brief(correction)))
    heading('How each agent analysed your code')
    story.append(p('Actual status, retained finding and evidence reference for every recorded agent. COMPLETED describes execution, not necessarily a passed property. No confidence percentage or execution claim is inferred.'))
    for a in result.get('agent_details',[]):
        heading(a['name']+' | '+a['status'])
        story.append(p(brief(a.get('result') or 'No result retained.',700)))
        outputs = list(dict.fromkeys(str(x) for x in a.get('outputs',[]) if x))
        if outputs: story.append(p('Recorded output: '+' | '.join(brief(x,220) for x in outputs[:3])))
        story.append(p('Evidence: '+(', '.join(a.get('evidence_ids',[])) or 'None')))
    heading('Tests to run after revision')
    story.append(p('Suggested tests have not been executed by this report generator. Compare against the assignment contract.'))
    table([['Case','Input','Expected check']] + [list(x) for x in proposed_tests(result.get('source',''),title)],[115,170,226])
    inputs = recorded_inputs(result)
    if inputs:
        heading('Retained symbolic inputs')
        for item in inputs[:5]: story.append(p(brief(item,400)))
    notes = result.get('retrieved_notes',[])
    if notes:
        heading('Course notes linked to your findings')
        for note in notes[:4]:
            story.append(p(brief(note.get('id','')+': '+note.get('title','')+' - '+str(note.get('text',note.get('content',''))),700)))
    heading('Submitted source and review map')
    source = result.get('source','')
    story.append(p('Source SHA-256: '+hashlib.sha256(source.encode()).hexdigest()))
    story.append(p('Line references above refer to this original submission. Full numbered source and technical logs remain available in the application.'))
    story.append(p('Only retained results are summarized. Approval and scores are preserved; this export does not rerun analysis or measure learning gains.'))
    def footer(c, doc):
        c.saveState();c.setFont(FONT,8);c.setFillColor(colors.HexColor('#52667b'))
        c.drawString(42,25,'GradeAI | Faculty-approved assessment');c.drawRightString(553,25,'Page '+str(doc.page));c.restoreState()
    SimpleDocTemplate(out, pagesize=(595.28,841.89),leftMargin=42,rightMargin=42,topMargin=32,bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
