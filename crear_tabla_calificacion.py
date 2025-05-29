from app import app, db
from app import Calificacion

with app.app_context():
    db.create_all()
    print("✅ Tabla 'calificacion' creada correctamente.")
