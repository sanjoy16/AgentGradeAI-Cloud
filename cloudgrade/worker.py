import logging
import uuid
import time
from datetime import timedelta
from sqlalchemy import select, update
from . import create_app
from .models import db, Submission, Audit, now
from .agents import evaluate
from .sandbox import DockerSandbox

log = logging.getLogger(__name__)

def process_one(sandbox=None):
    # Conditional UPDATE prevents duplicate claims across SQLite or PostgreSQL workers.
    candidate = db.session.scalar(select(Submission.id).where(Submission.status == 'queued').order_by(Submission.created_at).limit(1))
    if not candidate:
        return False
    token = str(uuid.uuid4())
    claim = db.session.execute(update(Submission).where(Submission.id == candidate, Submission.status == 'queued').values(status='evaluating', started_at=now(), job_token=token))
    db.session.commit()
    if claim.rowcount != 1:
        return True
    item = db.session.get(Submission, candidate)
    try:
        report = evaluate(item.source, item.tests, item.rubric, item.harness, sandbox or DockerSandbox())
        status, error = 'pending_review', None
    except Exception:
        log.exception('Evaluation failed for %s', candidate)
        report, status, error = None, 'failed', 'Evaluation failed. Faculty may retry the submission after inspecting worker logs.'
    result = db.session.execute(update(Submission).where(Submission.id == candidate, Submission.status == 'evaluating', Submission.job_token == token).values(report=report, status=status, error=error, completed_at=now()))
    if result.rowcount == 1:
        db.session.add(Audit(submission_id=candidate, action=status))
    db.session.commit()
    return True


def recover_stale():
    # Do not automatically re-run: faculty explicitly retries interrupted jobs.
    stale = db.session.scalars(select(Submission).where(Submission.status == 'evaluating', Submission.started_at < now() - timedelta(minutes=15))).all()
    for item in stale:
        changed = db.session.execute(update(Submission).where(Submission.id == item.id,
            Submission.status == 'evaluating', Submission.job_token == item.job_token,
            Submission.started_at < now() - timedelta(minutes=15)).values(
                status='failed', error='Worker lease expired; faculty may retry.'))
        if changed.rowcount == 1:
            db.session.add(Audit(submission_id=item.id, action='lease_expired'))

    db.session.commit()


def main():
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    with app.app_context():
        while True:
            try:
                recover_stale()
                if not process_one():
                    time.sleep(2)
                db.session.remove()
            except Exception:
                db.session.rollback()
                log.exception('Queue error')
                time.sleep(5)

if __name__ == '__main__':
    main()
