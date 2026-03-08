from flask_apscheduler import APScheduler
scheduler = APScheduler()


def increment_production_capacity():
    from .models import NationFactory
    from . import db
    with scheduler.app.app_context():
        NationFactory.query.filter(
            NationFactory.count > 0,
            NationFactory.production_capacity < 24
        ).update({'production_capacity': NationFactory.production_capacity + 1})
        db.session.commit()


def register_tasks(app):
    scheduler.init_app(app)
    scheduler.add_job(id='incr_prod_cap', func=increment_production_capacity, trigger='interval', hours=1)
    scheduler.start()
