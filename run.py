import os
from app import create_app, db

app = create_app(os.environ.get('FLASK_ENV', 'default'))


@app.cli.command('init-db')
def init_db():
    """Initialize the database."""
    db.create_all()
    print('Database initialized.')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
