import sqlite3

# Conectar a la base de datos
conn = sqlite3.connect('lavamovil.db')
cursor = conn.cursor()

# Obtener las columnas de la tabla usuario
cursor.execute("PRAGMA table_info(usuario)")
columnas = cursor.fetchall()

print("Columnas en la tabla 'usuario':")
for columna in columnas:
    print(f"- {columna[1]}")

conn.close()
