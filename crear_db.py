from app import app, db

# Necesitamos abrir el contexto de la app para trabajar con la base de datos
with app.app_context():
    db.create_all()
    print("✅ Base de datos creada correctamente.")
