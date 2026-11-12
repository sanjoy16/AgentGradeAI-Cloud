import click
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from .models import db, User, Assignment
from .agents import DEFAULT_WEIGHTS


def register(app):
    @app.cli.command('init-db')
    def init_db():
        """Initialize a fresh database. Back up before future schema migrations."""
        db.create_all()
        click.echo('Database tables initialized.')

    @app.cli.command('create-faculty')
    @click.option('--email', prompt=True)
    @click.option('--name', prompt=True)
    @click.password_option(confirmation_prompt=True)
    def create_faculty(email, name, password):
        if len(password) < 12 or len(password) > 128 or '@' not in email:
            raise click.ClickException('Use a valid email and a 12–128 character password.')
        email = email.strip().lower()
        if db.session.scalar(select(User).where(User.email == email)):
            raise click.ClickException('Email already registered; no role change made.')
        db.session.add(User(email=email, name=name[:120], password=generate_password_hash(password), role='faculty'))
        db.session.commit()
        click.echo('Faculty account created.')

    @app.cli.command('seed-assignment')
    def seed_assignment():
        if db.session.scalar(select(Assignment).limit(1)):
            raise click.ClickException('Assignments already exist; use the faculty dashboard.')
        db.session.add(Assignment(title='Sum of two integers', description='Read two integers from standard input and print their sum followed by a newline. Use C17. Check scanf return values. Inputs are in [-10000,10000].',
            tests=[{'stdin': '2 3\n', 'expected': '5\n'}, {'stdin': '-3 3\n', 'expected': '0\n'},
                   {'stdin': '10000 -9999\n', 'expected': '1\n'}], weights=DEFAULT_WEIGHTS, harness=''))
        db.session.commit()
        click.echo('Sample assignment created.')
