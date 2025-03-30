from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from datetime import datetime
import os

bauches_pendientes = []  # ✅ Aquí está bien

ubicaciones_en_memoria = {}

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lavamovil.db'
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"connect_args": {"check_same_thread": False}}
app.config['SECRET_KEY'] = 'tu_clave_secreta'  # Clave necesaria para las sesiones
app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024  # 3 MB máximo
db = SQLAlchemy(app)
socketio = SocketIO(app)

# Modelo de usuario con rol (cliente o lavador) y suscripción para lavadores
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), unique=True, nullable=False)
    rol = db.Column(db.String(20))  # 'cliente' o 'lavador'
    suscrito = db.Column(db.Boolean, default=False)  # Solo para lavadores
    descripcion = db.Column(db.Text, default="")     # Breve descripción o presentación
    telefono = db.Column(db.String(20), default="")    # Número de teléfono
    direccion = db.Column(db.String(200), default="")  # Dirección de su casa
    id_personal = db.Column(db.String(50), default="") # Número de identificación personal

# Modelo de solicitud de lavado con campo para calificación
class Solicitud(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    latitud = db.Column(db.Float, nullable=False)
    longitud = db.Column(db.Float, nullable=False)
    estado = db.Column(db.String(20), default='pendiente')  # pendiente, en_curso, completada
    lavador_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    lavador = db.relationship('Usuario', foreign_keys=[lavador_id])
    calificacion = db.Column(db.Integer)                    # Almacena la calificación

@app.route('/solicitar', methods=['POST'])
def solicitar_servicio():
    print("📨 El ID real del cliente que está creando la solicitud es:", session.get('user_id'))
    data = request.get_json()
    solicitud = Solicitud(
    cliente_id=session.get('user_id'),
        latitud=data['latitud'],
        longitud=data['longitud']
    )
    db.session.add(solicitud)
    db.session.commit()
    socketio.emit('nueva_solicitud', {
        'solicitud_id': solicitud.id,
        'latitud': solicitud.latitud,
        'longitud': solicitud.longitud
    })
    return jsonify({'mensaje': 'Solicitud creada', 'solicitud_id': solicitud.id}), 201

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(Usuario, session['user_id'])
    if not user:
        return redirect(url_for('login'))
    return render_template('chat.html', user=user)

@socketio.on('chat_message')
def handle_chat_message(data):
    emit('chat_message', data, broadcast=True)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        rol_input = request.form.get('rol')
        user = Usuario.query.filter_by(nombre=nombre).first()
        if user:
            if user.rol.lower().strip() == rol_input.lower().strip():
                session['user_id'] = user.id
                session['user_name'] = user.nombre
                if rol_input == 'cliente':
                    return redirect(url_for('cliente_dashboard'))
                elif rol_input == 'lavador':
                    if not user.descripcion or not user.telefono or not user.direccion or not user.id_personal:
                        return redirect(url_for('lavador_perfil'))
                    elif not user.suscrito:
                        return redirect(url_for('subscribe'))
                    else:
                        return redirect(url_for('lavador_dashboard'))
                elif rol_input == 'admin':
                    return redirect(url_for('admin_dashboard'))

        return "Usuario no encontrado", 404

    return render_template('login.html')

@app.route('/')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(Usuario, session['user_id'])
    if not user:
        return redirect(url_for('login'))
    print("User role:", repr(user.rol))
    rol = user.rol.lower().strip()
    if rol == 'lavador':
        # Verifica que el perfil del lavador esté completo:
        if not (user.descripcion and user.telefono and user.direccion and user.id_personal):
            return redirect(url_for('lavador_perfil'))
        return render_template('lavador_dashboard.html', user=user)
    elif rol == 'cliente':
        return render_template('client_dashboard.html', user=user)
    else:
        return "Rol desconocido", 400

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        rol = request.form.get('rol')
        if not nombre or not rol:
            return "Faltan datos", 400
        existing_user = Usuario.query.filter_by(nombre=nombre).first()
        if existing_user:
            return "El nombre de usuario ya existe. Por favor, elige otro.", 400
        nuevo_usuario = Usuario(nombre=nombre, rol=rol)
        db.session.add(nuevo_usuario)
        db.session.commit()

        socketio.emit('nuevo_registro', {'nombre': nuevo_usuario.nombre})

        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/aceptar', methods=['POST'])
def aceptar():
    if 'user_id' not in session:
        return jsonify({'error': 'Usuario no autenticado'}), 403

    user = db.session.get(Usuario, session['user_id'])

    if not user or user.rol != 'lavador':
        return jsonify({'error': 'Solo los lavadores pueden aceptar servicios'}), 403

    if not user.suscrito:
        return jsonify({'error': 'Debes suscribirte para aceptar servicios'}), 403

    data = request.get_json()
    solicitud_id = data.get('solicitud_id')
    solicitud = db.session.get(Solicitud, solicitud_id)

    if not solicitud or solicitud.estado != 'pendiente':
        return jsonify({'error': 'Solicitud inválida o ya fue aceptada'}), 400

    solicitud.estado = 'aceptado'
    solicitud.lavador_id = user.id
    db.session.commit()

    lavador_info = {
        'nombre': user.nombre,
        'descripcion': user.descripcion,
        'telefono': user.telefono,
        'direccion': user.direccion,
        'id_personal': user.id_personal
    }

    socketio.emit('solicitud_aceptada', {
        'solicitud_id': solicitud.id,
        'lavador': lavador_info,
        'latitud': solicitud.latitud,
        'longitud': solicitud.longitud
    })

    socketio.emit('nueva_solicitud', {
        'solicitud_id': solicitud.id,
        'latitud': solicitud.latitud,
        'longitud': solicitud.longitud
    })

    return jsonify({'mensaje': 'Solicitud aceptada correctamente'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/calificar', methods=['POST'])
def calificar():
    data = request.get_json()
    solicitud_id = data.get('solicitud_id')
    calificacion = data.get('calificacion')
    solicitud = db.session.get(Solicitud, solicitud_id)
    if solicitud:
        solicitud.estado = 'completada'
        solicitud.calificacion = calificacion
        db.session.commit()
        return jsonify({'mensaje': 'Servicio completado y calificación registrada'}), 200
    else:
        return jsonify({'mensaje': 'Solicitud no encontrada'}), 404

@app.route('/historial')
def historial():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(Usuario, session['user_id'])
    if not user:
        return redirect(url_for('login'))
    solicitudes = Solicitud.query.filter_by(cliente_id=user.id, estado='completada').all()
    return render_template('historial.html', solicitudes=solicitudes, user=user)

@app.route('/subscribe', methods=['GET', 'POST'])
def subscribe():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(Usuario, session['user_id'])
    if user.rol.lower().strip() != 'lavador':
        return "Solo los lavadores pueden suscribirse.", 403
    if request.method == 'POST':
        user.suscrito = True
        db.session.commit()
        return redirect(url_for('dashboard'))
    mensaje = request.args.get('enviado')
    return render_template('subscribe.html', user=user, mensaje=mensaje)

@app.route('/lavador_perfil', methods=['GET', 'POST'])
def lavador_perfil():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(Usuario, session['user_id'])
    if user is None:
        return redirect(url_for('login'))
    if user.rol.lower().strip() != 'lavador':
        return "Acceso denegado", 403
    if request.method == 'POST':
        print("Datos recibidos en POST:", request.form)
        descripcion = request.form.get('descripcion')
        telefono = request.form.get('telefono')
        direccion = request.form.get('direccion')
        id_personal = request.form.get('id_personal')
        user.descripcion = descripcion
        user.telefono = telefono
        user.direccion = direccion
        user.id_personal = id_personal
        db.session.commit()
        return redirect(url_for('subscribe'))
# 🔁 Comentado: print duplicado después de return
#         print("Perfil actualizado para el usuario", user.nombre)
        print("Perfil actualizado para el usuario", user.nombre)
        return redirect(url_for('dashboard'))
    return render_template('lavador_profile.html', user=user)

@app.route('/estado_suscripcion')
def estado_suscripcion():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(Usuario, session['user_id'])
    return f"Usuario: {user.nombre} – Suscrito: {user.suscrito}"

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': 'Suscripción LavaMóvil',
                        },
                        'unit_amount': 500,  # $5.00 USD
                    },
                    'quantity': 1,
                },
            ],
            mode='payment',
            success_url=url_for('success', _external=True),
            cancel_url=url_for('cancel', _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return jsonify(error=str(e)), 400

@app.route('/success')
def success():
    if 'user_id' in session:
        user = db.session.get(Usuario, session['user_id'])
        if user:
            user.suscrito = True
            db.session.commit()
    return render_template('success.html')

@app.route('/cancel')
def cancel():
    return "Suscripción cancelada. Puedes intentarlo de nuevo."

@app.route('/admin/lavadores')
def admin_lavadores():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    admin = db.session.get(Usuario, session['user_id'])
    if not admin or admin.rol != 'admin':
        return "Acceso denegado", 403

    lavadores = Usuario.query.filter_by(rol='lavador').all()
    return render_template('admin_lavadores.html', lavadores=lavadores)

@app.route('/admin/activar_suscripcion', methods=['POST'])
def activar_suscripcion():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    admin = db.session.get(Usuario, session['user_id'])
    if not admin or admin.rol != 'admin':
        return "Acceso denegado", 403

    user_id = request.form.get('user_id')
    lavador = db.session.get(Usuario, int(user_id))
    if lavador and lavador.rol == 'lavador':
        lavador.suscrito = True
        db.session.commit()
    
    return redirect(url_for('admin_lavadores'))

@app.route('/admin/desactivar_suscripcion', methods=['POST'])
def desactivar_suscripcion():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    admin = db.session.get(Usuario, session['user_id'])
    if not admin or admin.rol != 'admin':
        return "Acceso denegado", 403

    user_id = request.form.get('user_id')
    lavador = db.session.get(Usuario, int(user_id))
    if lavador and lavador.rol == 'lavador':
        lavador.suscrito = False
        db.session.commit()

    return redirect(url_for('admin_lavadores'))

@app.route('/admin/clientes')
def admin_clientes():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    admin = db.session.get(Usuario, session['user_id'])
    if not admin or admin.rol != 'admin':
        return "Acceso denegado", 403

    clientes = Usuario.query.filter_by(rol='cliente').all()
    return render_template('admin_clientes.html', clientes=clientes)

@app.route('/admin/eliminar_cliente', methods=['POST'])
def eliminar_cliente():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    admin = db.session.get(Usuario, session['user_id'])
    if not admin or admin.rol != 'admin':
        return "Acceso denegado", 403

    user_id = request.form.get('user_id')
    cliente = db.session.get(Usuario, int(user_id))
    if cliente and cliente.rol == 'cliente':
        db.session.delete(cliente)
        db.session.commit()

    return redirect(url_for('admin_clientes'))

@app.route('/admin/solicitudes')
def admin_solicitudes():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    admin = db.session.get(Usuario, session['user_id'])
    if not admin or admin.nombre != 'angelotrabajo97@gmail.com':
        return "Acceso denegado", 403

    solicitudes = Solicitud.query.order_by(Solicitud.id.desc()).all()
    for solicitud in solicitudes:
        solicitud.cliente = db.session.get(Usuario, solicitud.cliente_id) if solicitud.cliente_id else None
        solicitud.lavador = db.session.get(Usuario, solicitud.lavador_id) if solicitud.lavador_id else None

    return render_template('admin_solicitudes.html', solicitudes=solicitudes)

@app.route('/admin/eliminar_solicitud', methods=['POST'])
def eliminar_solicitud():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    admin = db.session.get(Usuario, session['user_id'])
    if not admin or admin.nombre != 'angelotrabajo97@gmail.com':
        return "Acceso denegado", 403

    solicitud_id = request.form.get('solicitud_id')
    solicitud = db.session.get(Solicitud, int(solicitud_id))
    if solicitud:
        db.session.delete(solicitud)
        db.session.commit()

    return redirect(url_for('admin_solicitudes'))

@app.route('/lavador_dashboard')
def lavador_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(Usuario, session['user_id'])
    if not user or user.rol.lower() != 'lavador':
        return "Acceso denegado", 403
    return render_template('lavador_dashboard.html', user=user)

@app.route('/lavador_trabajo')
def lavador_trabajo():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(Usuario, session['user_id'])

    if user.rol != 'lavador':
        return "Acceso denegado", 403

    return render_template('lavador_trabajo.html', user=user)

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(Usuario, session['user_id'])
    if user.rol != 'admin':
        return "Acceso denegado", 403

    return render_template('admin_dashboard.html', user=user)

@app.route('/cliente_dashboard')
def cliente_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(Usuario, session['user_id'])

    if user.rol != 'cliente':
        return "Acceso denegado", 403

    return render_template('client_dashboard.html', user=user)

@app.route('/ver_solicitudes')
# 🔹 Esta función parece no estar conectada a ninguna plantilla
def ver_solicitudes():
    solicitudes = Solicitud.query.all()
    resultado = []
    for s in solicitudes:
        resultado.append({
            'id': s.id,
            'cliente_id': s.cliente_id,
            'lavador_id': s.lavador_id,
            'estado': s.estado
        })
    return jsonify(resultado)

@app.route('/guardar_ubicacion', methods=['POST'])
def guardar_ubicacion():
    datos = request.get_json()
    lat = datos.get('lat')
    lng = datos.get('lng')
    tipo = datos.get('tipo')  # puede ser 'cliente' o 'lavador'

    if tipo not in ['cliente', 'lavador']:
        return jsonify({'error': 'Tipo inválido'}), 400

    ubicaciones_en_memoria[tipo] = {'lat': lat, 'lng': lng}

    return jsonify({'status': 'ok'})

@app.route('/obtener_ubicacion', methods=['GET'])
def obtener_ubicacion():
    tipo = request.args.get('tipo')  # cliente o lavador
    if tipo not in ['cliente', 'lavador']:
        return jsonify({'error': 'Tipo inválido'}), 400

    ubicacion = ubicaciones_en_memoria.get(tipo)
    if ubicacion:
        return jsonify(ubicacion)
    else:
        return jsonify({'lat': None, 'lng': None})

@app.route('/solicitud_activa')
def solicitud_activa():
    if 'user_id' not in session:
        return jsonify({'error': 'Usuario no autenticado'}), 403

    user = db.session.get(Usuario, session['user_id'])
    print("ID del cliente logueado:", user.id)
    print("🔄 Buscando solicitud 'pendiente' o 'aceptado' para cliente:", user.id)

    solicitud = Solicitud.query.filter(
        Solicitud.cliente_id == user.id,
        Solicitud.estado.in_(['pendiente', 'aceptado'])
    ).order_by(Solicitud.id.desc()).first()

    if not solicitud:
        return jsonify({'error': 'No hay solicitud activa'}), 404

    print("✅ Solicitud encontrada del cliente:", solicitud.cliente_id)
    return jsonify({'solicitud_id': solicitud.id})

@app.route('/cancelar_solicitud', methods=['POST'])
def cancelar_solicitud():
    if 'user_id' not in session:
        return jsonify({'error': 'Usuario no autenticado'}), 403

    user = db.session.get(Usuario, session['user_id'])

    solicitud = Solicitud.query.filter(
        Solicitud.cliente_id == user.id,
        Solicitud.estado.in_(['pendiente', 'aceptado'])
    ).order_by(Solicitud.id.desc()).first()

    if not solicitud:
        return jsonify({'error': 'No hay solicitud activa que cancelar'}), 404

    solicitud.estado = 'cancelado'
    db.session.commit()
    print("❌ Solicitud cancelada para cliente:", user.id)
    return jsonify({'mensaje': 'Solicitud cancelada correctamente'})

@socketio.on("ubicacion_lavador")
def handle_ubicacion_lavador(data):
    emit("lavador_ubicacion", data, broadcast=True)

@app.route('/terminos')
def terminos():
    return render_template('terminos.html')

@app.route('/admin_estadisticas')
def admin_estadisticas():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(Usuario, session['user_id'])
    if user.rol != 'admin':
        return "Acceso denegado", 403

    lavadores = Usuario.query.filter_by(rol='lavador').count()
    clientes = Usuario.query.filter_by(rol='cliente').count()
    solicitudes_totales = Solicitud.query.count()
    solicitudes_activas = Solicitud.query.filter_by(estado='pendiente').count()

    return render_template('admin_estadisticas.html',
                           lavadores=lavadores,
                           clientes=clientes,
                           solicitudes_totales=solicitudes_totales,
                           solicitudes_activas=solicitudes_activas)

@app.route('/subir_bauche', methods=['POST'])
def subir_bauche():
    if 'bauche' not in request.files:
        return "No se subió ningún archivo", 400

    archivo = request.files['bauche']
    if archivo.filename == '':
        return "Archivo inválido", 400

    if archivo:
        filename = secure_filename(archivo.filename)
        fecha = datetime.now().strftime("%Y%m%d%H%M%S")
        carpeta = os.path.join('static', 'bauches')
        os.makedirs(carpeta, exist_ok=True)  # 🔥 Asegura que la carpeta exista
        ruta_guardado = os.path.join(carpeta, f"{fecha}_{filename}")
        archivo.save(ruta_guardado)

        # Agregar notificación para el admin (nombre de archivo)
        bauches_pendientes.append(ruta_guardado)

        return redirect(url_for('subscribe', enviado='ok'))

@app.route('/ver_bauches')
def ver_bauches():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = db.session.get(Usuario, session['user_id'])
    if user.rol != 'admin':
        return "Acceso denegado", 403

    # Mostrar los bauches pendientes con su nombre (tomado del nombre del archivo)
    bauches = []
    carpeta = os.path.join('static', 'bauches')
    if os.path.exists(carpeta):
        for nombre_archivo in os.listdir(carpeta):
            ruta = os.path.join(carpeta, nombre_archivo)
            nombre_usuario = nombre_archivo.split("_", 1)[-1].split(".")[0]
            bauches.append((ruta, nombre_usuario))
    return render_template('ver_bauches.html', bauches=bauches)

@app.route('/aprobar_bauche', methods=['POST'])
def aprobar_bauche():
    ruta = request.form.get('ruta')
    nombre = request.form.get('nombre')
    if ruta and nombre:
        usuario = Usuario.query.filter_by(nombre=nombre).first()
        if usuario:
            usuario.suscrito = True
            db.session.commit()
        if os.path.exists(ruta):
            os.remove(ruta)
    return redirect(url_for('ver_bauches'))

if __name__ == "__main__":
    import os
    print("Directorio actual:", os.getcwd())
    with app.app_context():
        db.create_all()
        print("Base de datos creada o ya existente.")
    socketio.run(app, host="0.0.0.0")
# Despliegue forzado para Render

