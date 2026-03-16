import os
import sys

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User, Nation
from werkzeug.security import generate_password_hash

app = create_app(os.environ.get('FLASK_ENV', 'default'))

def seed_nations():
    with app.app_context():
        # Example data
        nations_data = [
            {
                "username": "us_test",
                "email": "us@example.com",
                "nation_name": "United States of America",
                "flag_url": "/uploads/flags/us.png",
                "population": 331000000,
                "population_gp": 331000,
                "land_gp": 100000,
                "factory_gp": 50000,
                "building_gp": 20000,
                "military_gp": 150000
            },
            {
                "username": "uk_test",
                "email": "uk@example.com",
                "nation_name": "United Kingdom",
                "flag_url": "/uploads/flags/gb.png",
                "population": 67000000,
                "population_gp": 67000,
                "land_gp": 20000,
                "factory_gp": 10000,
                "building_gp": 5000,
                "military_gp": 30000
            },
            {
                "username": "canada_test",
                "email": "canada@example.com",
                "nation_name": "Canada",
                "flag_url": "/uploads/flags/ca.png",
                "population": 38000000,
                "population_gp": 38000,
                "land_gp": 50000,
                "factory_gp": 8000,
                "building_gp": 4000,
                "military_gp": 15000
            },
            {
                "username": "france_test",
                "email": "france@example.com",
                "nation_name": "France",
                "flag_url": "/uploads/flags/fr.png",
                "population": 65000000,
                "population_gp": 65000,
                "land_gp": 25000,
                "factory_gp": 12000,
                "building_gp": 6000,
                "military_gp": 35000
            },
            {
                "username": "germany_test",
                "email": "germany@example.com",
                "nation_name": "Germany",
                "flag_url": "/uploads/flags/de.png",
                "population": 83000000,
                "population_gp": 83000,
                "land_gp": 15000,
                "factory_gp": 18000,
                "building_gp": 7000,
                "military_gp": 25000
            }
        ]

        for data in nations_data:
            user = User.query.filter_by(username=data['username']).first()
            if not user:
                user = User(
                    username=data['username'],
                    email=data['email'],
                    password_hash=generate_password_hash('password123'),
                    vacation_mode=True
                )
                db.session.add(user)
                db.session.flush() # To get user.id

            nation = Nation.query.filter_by(user_id=user.id).first()
            if not nation:
                nation = Nation(
                    user_id=user.id,
                    name=data['nation_name'],
                    flag_url=data['flag_url'],
                    population=data['population'],
                    population_gp=data['population_gp'],
                    land_gp=data['land_gp'],
                    factory_gp=data['factory_gp'],
                    building_gp=data['building_gp'],
                    military_gp=data['military_gp']
                )
                db.session.add(nation)
            else:
                # Update if already exists
                nation.name = data['nation_name']
                nation.flag_url = data['flag_url']
                nation.population = data['population']
                nation.population_gp = data['population_gp']
                nation.land_gp = data['land_gp']
                nation.factory_gp = data['factory_gp']
                nation.building_gp = data['building_gp']
                nation.military_gp = data['military_gp']
                user.vacation_mode = True

        db.session.commit()
        print(f"Successfully seeded {len(nations_data)} example nations.")

if __name__ == '__main__':
    seed_nations()
