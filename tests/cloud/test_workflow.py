import io
from copy import deepcopy
import pytest
from sqlalchemy import select
from cloudgrade.models import db, User, Assignment, Submission, Audit
from cloudgrade.worker import process_one
from cloudgrade.agents import DEFAULT_WEIGHTS, evaluate, validate_weights
from conftest import sign_in, FakeSandbox

SOURCE = '#include <stdio.h>\nint main(void){int a,b; if(scanf("%d%d",&a,&b)!=2)return 1;printf("%d\\n",a+b);return 0;}'

def submit(client):
    sign_in(client, 1)
    response = client.post('/submit', data={'assignment_id': '1', 'title': 'My solution', 'notes': 'My approach', 'source': (io.BytesIO(SOURCE.encode()), 'sum.c')})
    assert response.status_code == 302
    return response.location


def test_complete_approval_flow_and_confidentiality(app, client):
    path = submit(client)
    sid = path.split('/')[-1]
    assert process_one(FakeSandbox())
    item = db.session.get(Submission, sid)
    assert item.status == 'pending_review'
    assert item.report['unassessed_weight'] == 15
    assert not process_one(FakeSandbox())
    page = client.get(path)
    assert b'awaiting faculty review' in page.data
    assert b'GCC C17' not in page.data
    assert client.get(path + '/report.pdf').status_code == 403
    sign_in(client, 2)
    for suffix in ['', '/source.c', '/report.pdf']:
        assert client.get(path + suffix).status_code == 404
    assert client.post('/faculty/' + sid + '/approve').status_code == 403
    sign_in(client, 3)
    assert b'GCC C17' in client.get(path).data
    form = {'score_' + a['key']: str(a['score'] if a['score'] is not None else 0) for a in item.report['agents']}
    form.update(feedback='Good test coverage. Document complexity and check bounds.', reason='Reviewed all tool evidence and missing contract checks.', confirm='yes')
    result = client.post('/faculty/' + sid + '/approve', data=form)
    assert result.status_code == 302
    db.session.expire_all()
    item = db.session.get(Submission, sid)
    assert item.status == 'approved'
    assert item.approved_by == 3
    assert b'Faculty-approved assessment' in client.get(path).data
    assert item.approved_report['score'] == sum(a['score'] for a in item.approved_report['agents'])
    assert db.session.scalar(select(Audit).where(Audit.action == 'approved')).detail['changes']
    # Immutable publication: subsequent approvals and retries are rejected.
    assert client.post('/faculty/' + sid + '/approve', data=form).status_code == 409
    assert client.post('/faculty/' + sid + '/retry').status_code == 409
    sign_in(client, 1)
    assert b'Document complexity' in client.get(path).data
    pdf = client.get(path + '/report.pdf')
    assert pdf.status_code == 200 and pdf.data.startswith(b'%PDF-')

@pytest.mark.parametrize('invalid', ['nan', 'inf', '-1', '101', ''])
def test_invalid_marks_do_not_publish(app, client, invalid):
    path = submit(client)
    process_one(FakeSandbox())
    sid = path.split('/')[-1]
    item = db.session.get(Submission, sid)
    sign_in(client, 3)
    form = {'score_' + a['key']: '0' for a in item.report['agents']}
    form.update(score_compilation=invalid, feedback='Detailed feedback', reason='Manual review complete', confirm='yes')
    client.post('/faculty/' + sid + '/approve', data=form)
    db.session.expire_all()
    assert db.session.get(Submission, sid).status == 'pending_review'


def test_snapshot_upload_validation_and_escape(app, client):
    path = submit(client)
    item = db.session.get(Submission, path.split('/')[-1])
    assignment = db.session.get(Assignment, 1)
    assignment.weights = dict(DEFAULT_WEIGHTS, compilation=0, functionality=45)
    assignment.tests = [{'stdin': '0 0', 'expected': '0'}]
    item.notes = '<script>alert(1)</script>'
    db.session.commit()
    assert item.rubric['compilation'] == 15
    assert item.tests[0]['expected'] == '5\n'
    page = client.get(path).data
    assert b'<script>alert' not in page and b'&lt;script&gt;' in page
    for raw, name in [(b'\xff', 'bad.c'), (b'a' * 65537, 'big.c'), (b'int main(){}', 'bad.zip')]:
        response = client.post('/submit', data={'assignment_id': '1', 'title': 'Bad', 'source': (io.BytesIO(raw), name)})
        assert response.status_code == 200
    assert len(db.session.scalars(select(Submission)).all()) == 1


def test_auth_and_role_not_user_controlled(app, client):
    assert client.get('/dashboard').status_code == 302
    client.post('/register', data={'name': 'New Student', 'email': 'new@example.edu', 'student_id': 'X', 'password': 'long-password-123', 'role': 'faculty'})
    user = db.session.scalar(select(User).where(User.email == 'new@example.edu'))
    assert user.role == 'student'
    assert client.get('/faculty/assignments').status_code == 403
    client.post('/logout')
    assert client.post('/login', data={'email': 'student@example.edu', 'password': 'student-password'}).status_code == 302
    assert client.get('/dashboard').status_code == 200


def test_csrf_is_enforced(app, client):
    app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/login', data={'email': 'a', 'password': 'b'}).status_code == 400


def test_unavailable_evidence_never_passes():
    class Broken:
        def run(self, *args):
            raise RuntimeError('worker down')
    result = evaluate(SOURCE, [{'stdin': '', 'expected': ''}], DEFAULT_WEIGHTS, '', Broken())
    by_key = {a['key']: a for a in result['agents']}
    for key in ['compilation', 'functionality', 'optimization', 'security', 'formal', 'symbolic', 'complexity']:
        assert by_key[key]['score'] is None
    assert result['unassessed_weight'] == 80
    assert result['score'] <= 20


def test_weights_must_total_100():
    with pytest.raises(ValueError):
        validate_weights(dict(DEFAULT_WEIGHTS, compilation=16))
    with pytest.raises(ValueError):
        validate_weights(dict(DEFAULT_WEIGHTS, compilation=True))


def test_faculty_assignment_management(app, client):
    sign_in(client, 3)
    assert client.get('/faculty/assignments').status_code == 200
    assert client.post('/faculty/assignments/1/toggle').status_code == 302
    assert not db.session.get(Assignment, 1).active
    sign_in(client, 1)
    response = client.post('/submit', data={'assignment_id': '1', 'title': 'Closed', 'source': (io.BytesIO(SOURCE.encode()), 'sum.c')})
    assert response.status_code == 200
    assert not db.session.scalars(select(Submission)).all()
