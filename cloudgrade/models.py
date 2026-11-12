from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def now():
    return datetime.now(timezone.utc)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    student_id = db.Column(db.String(80), default='')
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(12), default='student', nullable=False)

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False)
    tests = db.Column(db.JSON, nullable=False)
    weights = db.Column(db.JSON, nullable=False)
    # Trusted faculty-authored harness, appended to source for CBMC/KLEE.
    harness = db.Column(db.Text, default='')
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=now)

class Submission(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    notes = db.Column(db.Text, default='')
    filename = db.Column(db.String(120), nullable=False)
    source = db.Column(db.Text, nullable=False)
    source_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(24), default='queued', nullable=False, index=True)
    report = db.Column(db.JSON)
    approved_report = db.Column(db.JSON)
    rubric = db.Column(db.JSON, nullable=False)
    tests = db.Column(db.JSON, nullable=False)
    harness = db.Column(db.Text, default='')
    feedback = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    job_token = db.Column(db.String(36))
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    approved_at = db.Column(db.DateTime(timezone=True))
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    error = db.Column(db.Text)
    student = db.relationship(User, foreign_keys=[user_id])
    assignment = db.relationship(Assignment)

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    submission_id = db.Column(db.String(36), index=True)
    action = db.Column(db.String(80), nullable=False)
    detail = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), default=now)
