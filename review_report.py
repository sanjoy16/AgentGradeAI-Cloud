"""Decision-focused presentation of recorded evidence; never executes tools or changes marks."""
from io import BytesIO
import hashlib
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from student_report import FONT, BOLD, deductions
from detailed_report import proposed_tests, recorded_inputs
from student_guidance import readable, repair_cards, agent_help


def brief(value, limit=700):
    text = ' '.join(readable(value).split())
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
    profile=result.get('assignment_profile','main')
    story.append(p('What was checked: '+('Program safety checks; printed factorial answers were not compared with expected output.' if profile=='main' else 'The selected function contract, within its stated input range.')))
    story.append(p('How to read this report: a code warning suggests a repair; an incomplete tool check needs review; held marks mean credit has not yet been verified.'))
    if result.get('review_required'):
        story.append(p('Review flag recorded: incomplete checks or findings require interpretation within the checked scope. Faculty approval does not turn incomplete checks into passes.'))
    heading('Rubric breakdown')
    table([['Criterion','Status / basis','Points']] + [[r['criterion'],brief(r.get('status','')+' - '+r.get('analysis',''),350),f"{r['score']}/{r['max']}"] for r in result.get('rubric',[])],[135,306,70])
    heading('Faculty feedback')
    story.append(p(brief(result.get('faculty_note') or 'No additional faculty comments.',1800)))
    heading('Your improvement plan: what to change first')
    story.append(p('The examples below are teaching suggestions based on the source and retained warnings. They were not executed by the report generator and do not add new deductions.'))
    for card in repair_cards(result):
        block_start=len(story)
        heading(card['title']+' - '+card['where'])
        for label,key in [('Why it matters','why'),('What to change','change')]:
            story.append(p(label+': '+card[key]))
        for line in card['example'].splitlines(): story.append(p(line))
        story.append(p('Check your repair: '+card['test']))
        block=story[block_start:]; del story[block_start:]; story.append(KeepTogether(block))
    heading('Why marks were lost or held')
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
        block_start=len(story)
        heading(a['name']+' | '+a['status'])
        meaning,action=agent_help(a)
        story.append(p('What it checked: '+meaning))
        story.append(p('Recorded finding: '+brief(a.get('result') or 'No result retained.',450)))
        story.append(p('What you should do: '+action))
        outputs = list(dict.fromkeys(str(x) for x in a.get('outputs',[]) if x))
        if a['key'] in ('symbolic','verification') and outputs:
            story.append(p('Check details: '+' | '.join(brief(x,200) for x in outputs[:3])))
        story.append(p('Evidence: '+(', '.join(a.get('evidence_ids',[])) or 'None')))
        block=story[block_start:]; del story[block_start:]; story.append(KeepTogether(block))
    heading('Tests to run after revision')
    story.append(p('Suggested tests have not been executed by this report generator. Compare against the assignment contract.'))
    table([['Case','Input','Expected check']] + [list(x) for x in proposed_tests(result.get('source',''),title)],[115,170,226])
    inputs = []  # Harness-internal nondeterministic objects are not student input examples.
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
