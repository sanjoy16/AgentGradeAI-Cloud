from copy import deepcopy
from functools import wraps
import hashlib
import json
import math
import uuid
from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for, Response
from sqlalchemy import select, update, func
from werkzeug.security import check_password_hash, generate_password_hash
from . import limiter
from .agents import DEFAULT_WEIGHTS, validate_weights
from .models import db, User, Assignment, Submission, Audit, now
from .pdf import build_pdf

bp = Blueprint('web', __name__)

@bp.before_request
def load_user():
    g.user = db.session.get(User, session['uid']) if session.get('uid') else None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.user:
            return redirect(url_for('web.login'))
        return f(*args, **kwargs)
    return decorated


def faculty_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if g.user.role != 'faculty':
            abort(403)
        return f(*args, **kwargs)
    return decorated


def submission_or_404(sid):
    item = db.session.get(Submission, sid)
    if not item or (g.user.role != 'faculty' and item.user_id != g.user.id):
        abort(404)
    return item

@bp.get('/')
def home():
    if g.user:
        return redirect(url_for('web.dashboard'))
    return render_template('home.html')

@bp.route('/register', methods=['GET', 'POST'])
@limiter.limit('10/hour', methods=['POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        name = request.form.get('name', '').strip()
        student_id = request.form.get('student_id', '').strip()
        password = request.form.get('password', '')
        if not (3 <= len(name) <= 120 and 3 <= len(email) <= 254 and '@' in email and 1 <= len(student_id) <= 80 and 12 <= len(password) <= 128):
            flash('Provide valid details and a password between 12 and 128 characters.', 'error')
        elif db.session.scalar(select(User).where(User.email == email)):
            flash('Unable to register with those details. Try signing in.', 'error')
        else:
            user = User(email=email, name=name, student_id=student_id, password=generate_password_hash(password), role='student')
            db.session.add(user)
            db.session.commit()
            session.clear()
            session['uid'] = user.id
            session.permanent = True
            return redirect(url_for('web.dashboard'))
    return render_template('auth.html', mode='register')

@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10/minute', methods=['POST'])
def login():
    if request.method == 'POST':
        user = db.session.scalar(select(User).where(User.email == request.form.get('email', '').strip().lower()))
        password = request.form.get('password', '')
        valid = check_password_hash(user.password, password) if user else check_password_hash(DUMMY_PASSWORD, password)
        if user and valid:
            session.clear()
            session['uid'] = user.id
            session.permanent = True
            return redirect(url_for('web.dashboard'))
        flash('Email or password is incorrect.', 'error')
    return render_template('auth.html', mode='login')

DUMMY_PASSWORD = generate_password_hash('dummy-value-not-an-account')

@bp.post('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('web.home'))

@bp.get('/dashboard')
@login_required
def dashboard():
    query = select(Submission)
    if g.user.role != 'faculty':
        query = query.where(Submission.user_id == g.user.id)
    status_filter = request.args.get('status', '')
    count_query = select(Submission.status, func.count()).group_by(Submission.status)
    if g.user.role != 'faculty':
        count_query = count_query.where(Submission.user_id == g.user.id)
    counts = {status: 0 for status in ['queued', 'evaluating', 'pending_review', 'approved', 'failed']}
    counts.update(dict(db.session.execute(count_query).all()))
    if status_filter in counts:
        query = query.where(Submission.status == status_filter)
    else:
        status_filter = ''
    page = max(1, request.args.get('page', 1, type=int))
    pagination = db.paginate(query.order_by(Submission.created_at.desc()), page=page, per_page=25, error_out=False)
    assignments = db.session.scalars(select(Assignment).where(Assignment.active.is_(True))).all()
    return render_template('dashboard.html', items=pagination.items, assignments=assignments, counts=counts,
                           pagination=pagination, status_filter=status_filter)


@bp.route('/submit', methods=['GET', 'POST'])
@login_required
@limiter.limit('15/hour', methods=['POST'])
def submit():
    assignments = db.session.scalars(select(Assignment).where(Assignment.active.is_(True))).all()
    if request.method == 'POST':
        assignment = db.session.get(Assignment, request.form.get('assignment_id', type=int))
        upload = request.files.get('source')
        title = request.form.get('title', '').strip()
        notes = request.form.get('notes', '').strip()
        if not assignment or not assignment.active or not upload or not upload.filename or not upload.filename.lower().endswith('.c') or not 1 <= len(title) <= 160 or len(notes) > 4000:
            flash('Select an active assignment, provide a title, and upload one UTF-8 .c file.', 'error')
        else:
            raw = upload.read(65537)
            try:
                source = raw.decode('utf-8')
                if not source.strip() or '\x00' in source or len(raw) > 65536:
                    raise ValueError()
            except (UnicodeError, ValueError):
                flash('The C file must contain UTF-8 text and be at most 64 KB.', 'error')
                return render_template('submit.html', assignments=assignments)
            item = Submission(id=str(uuid.uuid4()), user_id=g.user.id, assignment_id=assignment.id,
                title=title, notes=notes, source=source, filename=upload.filename.replace('\\', '/').split('/')[-1][:120],
                source_hash=hashlib.sha256(raw).hexdigest(), rubric=deepcopy(assignment.weights),
                tests=deepcopy(assignment.tests), harness=assignment.harness)
            db.session.add(item)
            db.session.add(Audit(actor_id=g.user.id, submission_id=item.id, action='submitted'))
            db.session.commit()
            return redirect(url_for('web.detail', sid=item.id))
    return render_template('submit.html', assignments=assignments)

@bp.get('/submissions/<sid>')
@login_required
def detail(sid):
    item = submission_or_404(sid)
    # Report confidentiality is enforced here, not merely by hiding UI controls.
    report = item.approved_report if item.status == 'approved' else item.report if g.user.role == 'faculty' else None
    audit = db.session.scalars(select(Audit).where(Audit.submission_id == sid).order_by(Audit.created_at)).all() if g.user.role == 'faculty' else []
    return render_template('detail.html', item=item, report=report, audit=audit)

@bp.get('/submissions/<sid>/report.pdf')
@login_required
def report_pdf(sid):
    item = submission_or_404(sid)
    if item.status != 'approved' or not item.approved_report:
        abort(403)
    return Response(build_pdf(item, item.approved_report), mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="AgentGradeAI-{item.id}.pdf"'})

@bp.get('/submissions/<sid>/source.c')
@login_required
def source_download(sid):
    item = submission_or_404(sid)
    return Response(item.source, mimetype='text/plain', headers={'Content-Disposition': 'attachment; filename="submission.c"'})

@bp.post('/faculty/<sid>/approve')
@faculty_required
def approve(sid):
    item = submission_or_404(sid)
    if item.status != 'pending_review' or not item.report:
        abort(409)
    report = deepcopy(item.report)
    reason = request.form.get('reason', '').strip()
    feedback = request.form.get('feedback', '').strip()
    if not feedback or len(feedback) > 8000 or not 5 <= len(reason) <= 2000:
        flash('Provide feedback and a review rationale (at least 5 characters).', 'error')
        return redirect(url_for('web.detail', sid=sid))
    changes = []
    try:
        for a in report['agents']:
            raw = request.form.get('score_' + a['key'], '').strip()
            if not raw:
                # Missing checks need explicit faculty judgment, including explicit zero.
                raise ValueError()
            score = float(raw)
            if not math.isfinite(score) or score < 0 or score > a['maximum']:
                raise ValueError()
            if a['score'] is None or score != a['score']:
                changes.append(dict(agent=a['key'], before=a['score'], after=score))
                a['original_score'] = a['score']
                a['score'] = round(score, 2)
                a['override_reason'] = reason
    except ValueError:
        flash('Enter a valid mark for every agent, including unavailable checks. Each mark must be within its maximum.', 'error')
        return redirect(url_for('web.detail', sid=sid))
    if request.form.get('confirm') != 'yes':
        abort(400)
    report['score'] = round(sum(a['score'] for a in report['agents']), 2)
    report['faculty_feedback'] = feedback
    report['review_rationale'] = reason
    report['summary'] = 'Faculty-approved assessment. Tool limitations remain recorded in each agent analysis. Faculty overrides are identified.'
    report['unassessed_weight'] = 0
    approved_at = now()
    result = db.session.execute(update(Submission).where(Submission.id == sid, Submission.status == 'pending_review').values(
        approved_report=report, status='approved', approved_by=g.user.id, approved_at=approved_at, feedback=feedback))
    if result.rowcount != 1:
        db.session.rollback()
        abort(409)
    db.session.add(Audit(actor_id=g.user.id, submission_id=sid, action='approved', detail=dict(changes=changes, reason=reason, score=report['score'])))
    db.session.commit()
    flash('Results approved and published to the student.', 'success')
    return redirect(url_for('web.detail', sid=sid))

@bp.post('/faculty/<sid>/retry')
@faculty_required
def retry(sid):
    item = submission_or_404(sid)
    if item.status not in ('failed', 'pending_review'):
        abort(409)
    result = db.session.execute(update(Submission).where(Submission.id == sid, Submission.status.in_(['failed', 'pending_review'])).values(status='queued', report=None, error=None, job_token=None))
    if result.rowcount != 1:
        db.session.rollback()
        abort(409)
    db.session.add(Audit(actor_id=g.user.id, submission_id=sid, action='retry'))
    db.session.commit()
    return redirect(url_for('web.detail', sid=sid))

@bp.route('/faculty/assignments', methods=['GET', 'POST'])
@faculty_required
def assignments():
    if request.method == 'POST':
        try:
            weights = validate_weights(json.loads(request.form.get('weights', '{}')))
            tests = json.loads(request.form.get('tests', '[]'))
            if not isinstance(tests, list) or not 1 <= len(tests) <= 10 or any(not isinstance(t, dict) or set(t) != {'stdin', 'expected'} or any(not isinstance(v, str) or len(v) > 4000 for v in t.values()) for t in tests):
                raise ValueError('Provide 1–10 tests with stdin and expected text fields, at most 4000 characters each.')
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            harness = request.form.get('harness', '')
            if not 1 <= len(title) <= 160 or not 1 <= len(description) <= 8000 or len(harness) > 16000:
                raise ValueError('Provide a title and instructions within the length limits.')
            item = Assignment(title=title, description=description, tests=tests, weights=weights, harness=harness)
            db.session.add(item)
            db.session.add(Audit(actor_id=g.user.id, action='assignment_created', detail={'title': title}))
            db.session.commit()
            flash('Assignment created. New submissions snapshot its tests and rubric.', 'success')
            return redirect(url_for('web.assignments'))
        except (ValueError, TypeError) as exc:
            flash(str(exc), 'error')
    items = db.session.scalars(select(Assignment).order_by(Assignment.id.desc())).all()
    return render_template('assignments.html', assignments=items, weights=json.dumps(DEFAULT_WEIGHTS, indent=2))

@bp.post('/faculty/assignments/<int:aid>/toggle')
@faculty_required
def toggle_assignment(aid):
    item = db.session.get(Assignment, aid)
    if not item:
        abort(404)
    item.active = not item.active
    db.session.add(Audit(actor_id=g.user.id, action='assignment_toggled', detail={'id': aid, 'active': item.active}))
    db.session.commit()
    return redirect(url_for('web.assignments'))

@bp.get('/healthz')
def health():
    db.session.execute(select(1))
    return {'status': 'ok'}
