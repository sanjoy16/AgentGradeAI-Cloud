import pytest
from werkzeug.security import generate_password_hash
from cloudgrade import create_app
from cloudgrade.models import db, User, Assignment
from cloudgrade.agents import DEFAULT_WEIGHTS

@pytest.fixture()
def app():
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret-' * 4, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'WTF_CSRF_ENABLED': False, 'SESSION_COOKIE_SECURE': False, 'RATELIMIT_ENABLED': False})
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id=1, email='student@example.edu', name='Student One', student_id='S001', password=generate_password_hash('student-password')),
                           User(id=2, email='other@example.edu', name='Student Two', student_id='S002', password=generate_password_hash('other-password')),
                           User(id=3, email='faculty@example.edu', name='Faculty One', password=generate_password_hash('faculty-password'), role='faculty')])
        db.session.add(Assignment(id=1, title='Sum', description='Read and add two integers.', weights=DEFAULT_WEIGHTS,
                                  tests=[{'stdin': '2 3\n', 'expected': '5\n'}], harness=''))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture()
def client(app):
    return app.test_client()


def sign_in(client, uid):
    with client.session_transaction() as session:
        session['uid'] = uid

class FakeSandbox:
    def run(self, source, action, tests=None, harness=''):
        if action == 'tests':
            return {'compile': {'code': 0, 'stdout': '', 'stderr': ''}, 'cases': [{'index': 1, 'passed': True, 'code': 0, 'stdout': '5\n', 'stderr': ''}]}
        if action in ('formal', 'symbolic'):
            return {'unavailable': 'No harness configured.'}
        return {'code': 0, 'stdout': '', 'stderr': ''}
