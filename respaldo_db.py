import shutil
import datetime
import os

# Crear carpeta 'respaldos' si no existe
os.makedirs("respaldos", exist_ok=True)

# Ruta original de tu base de datos
origen = "lavamovil.db"

# Nombre del archivo de respaldo con fecha automática
fecha = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
destino = os.path.join("respaldos", f"respaldo_lavamovil_{fecha}.db")

# Realiza la copia
shutil.copy2(origen, destino)
print(f"✅ Respaldo guardado como: {destino}")
