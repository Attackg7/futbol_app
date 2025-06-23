from flask import Flask, render_template, redirect, request, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Partido, Inscripcion, Calificacion, Amistad, Invitacion, Notificacion
import os
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime, timezone
from models import Notificacion
from flask_migrate import Migrate
from dotenv import load_dotenv
from flask import current_app
import secrets
from flask_mail import Mail, Message


app = Flask(__name__)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'davstegonzalez@gmail.com'
app.config['MAIL_PASSWORD'] = 'rtki lubm kikp wjdo' 
app.config['MAIL_DEFAULT_SENDER'] = 'davstegonzalez@gmail.com'


mail = Mail(app)

now = datetime.now()
load_dotenv()

app.secret_key = '123456'
app.config['SECRET_KEY'] = 'clave_supersecreta'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'futbol.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['GOOGLE_MAPS_API_KEY'] = os.environ.get('GOOGLE_MAPS_API_KEY')
# Inicializar extensiones
db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'inicio'  # Redirige a /login si no está logueado

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Página principal




from datetime import datetime
@app.route('/', methods=['GET', 'POST'])
def inicio():
    error = None
    mode = request.form.get('mode', 'login')
    next_page = request.args.get('next')

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        if mode == 'login':
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password, password):
                login_user(user)
                return redirect(next_page or url_for('index'))
            error = "Usuario o contraseña incorrectos"

        elif mode == 'register':
            nombre = request.form.get('nombre')
            apellido = request.form.get('apellido')
            pais = request.form.get('pais')
            ciudad = request.form.get('ciudad')
            telefono = request.form.get('telefono')

            if User.query.filter_by(email=email).first():
                error = "El correo electrónico ya está registrado."
            else:
                hashed_pw = generate_password_hash(password)
                username = f"{nombre.lower()}.{apellido.lower()}"
                # Asegura unicidad por si ya existe ese username
                base_username = username
                i = 1
                while User.query.filter_by(username=username).first():
                    username = f"{base_username}{i}"
                    i += 1

                nuevo_usuario = User(
                    username=username,
                    email=email,
                    password=hashed_pw,
                    nombre=nombre,
                    apellido=apellido,
                    pais=pais,
                    ciudad=ciudad,
                    telefono=telefono
                )
                db.session.add(nuevo_usuario)
                db.session.commit()
                flash("Cuenta creada exitosamente. Ahora puedes iniciar sesión.", "success")
                return redirect(url_for('inicio'))

        elif mode == 'reset':
            user = User.query.filter_by(email=email).first()
            if user:
                user.password = generate_password_hash(password)
                db.session.commit()
                flash("Contraseña restablecida exitosamente. Inicia sesión con tu nueva clave.", "success")
                return redirect(url_for('inicio'))
            error = "Usuario no encontrado"

    return render_template("inicio.html", now=datetime.now())


@app.before_request
def mostrar_mensaje_si_redirigido():
    if not current_user.is_authenticated and request.endpoint == 'inicio':
        if request.args.get('next'):
            flash("Primero debes iniciar sesión para acceder a esa página.", "warning")


@app.route('/eventos')
def index():
    partidos = Partido.query.order_by(Partido.fecha_hora.desc()).all()
    datos_partidos = []
    now = datetime.now()

    for partido in partidos:
        inscripciones = partido.inscripciones
        count_total = len(inscripciones)
        total_requerido = partido.max_jugadores * 2
        porcentaje_actual = count_total / total_requerido if total_requerido > 0 else 0

        tiempo_desde_inicio = (now - partido.fecha_hora).total_seconds()
        ha_empezado = partido.fecha_hora <= now
        ha_pasado_10_min = tiempo_desde_inicio >= 600
        ha_pasado_2_horas = tiempo_desde_inicio >= 7200
        ha_pasado_24_horas = tiempo_desde_inicio >= 86400

        cancelado_por_falta = False
        es_organizador = current_user.is_authenticated and current_user.id == partido.organizador_id

        # ✅ CANCELADO POR FALTA (<70%) Y ELIMINACIÓN A LOS 10 MIN
        if not partido.cerrado and ha_empezado and porcentaje_actual < 0.7:
            if ha_pasado_10_min:
                db.session.delete(partido)
                db.session.commit()
                continue  # Partido eliminado, no mostrar
            else:
                partido.cancelado = True  # Marcar como cancelado
                db.session.commit()
                cancelado_por_falta = True

        # ✅ ELIMINACIÓN POR NO TENER RESULTADO A LAS 24 HORAS
        if not partido.cerrado and ha_empezado and partido.resultado is None and ha_pasado_24_horas:
            for inscripcion in partido.inscripciones:
                db.session.delete(inscripcion)
            db.session.delete(partido)
            db.session.commit()
            continue  # Partido eliminado, no mostrar

        # Mostrar botón de resultado 2 horas después
        puede_registrar_resultado = (
            current_user.is_authenticated and
            current_user.id == partido.organizador_id and
            not partido.cerrado and
            partido.resultado is None and
            ha_pasado_2_horas and
            porcentaje_actual >= 0.7
        )

        # Conteo por equipos
        count_equipo1 = sum(1 for i in inscripciones if i.equipo == partido.equipo1)
        count_equipo2 = sum(1 for i in inscripciones if i.equipo == partido.equipo2)
        equipo1_lleno = count_equipo1 >= partido.max_jugadores
        equipo2_lleno = count_equipo2 >= partido.max_jugadores
        cupo_disponible = not (equipo1_lleno and equipo2_lleno)

        user_inscrito = False
        puede_calificar = False
        if current_user.is_authenticated:
            user_inscrito = any(i.user_id == current_user.id for i in inscripciones)
            if user_inscrito and partido.cerrado:
                jugadores_a_calificar = [i.user_id for i in inscripciones if i.user_id != current_user.id]
                ya_calificados = [
                    c.evaluado_id for c in partido.calificaciones
                    if c.evaluador_id == current_user.id
                ]
                puede_calificar = any(uid not in ya_calificados for uid in jugadores_a_calificar)

        datos_partidos.append({
            'partido': partido,
            'count_equipo1': count_equipo1,
            'count_equipo2': count_equipo2,
            'equipo1_lleno': equipo1_lleno,
            'equipo2_lleno': equipo2_lleno,
            'cupo_disponible': cupo_disponible,
            'user_inscrito': user_inscrito,
            'puede_calificar': puede_calificar,
            'cancelado_por_falta': cancelado_por_falta,
            'porcentaje_inscritos': porcentaje_actual,
            'puede_registrar_resultado': puede_registrar_resultado
        })

    # Clasificar
    proximos = []
    en_curso = []
    terminados = []

    for datos in datos_partidos:
        partido = datos['partido']
        cancelado = datos['cancelado_por_falta']
        porcentaje = datos['porcentaje_inscritos']
        ya_empezo = partido.fecha_hora <= now

        if cancelado or partido.cancelado:
            terminados.append(datos)
        elif partido.cerrado or partido.resultado:
            terminados.append(datos)
        elif ya_empezo and porcentaje >= 0.7:
            en_curso.append(datos)
        else:
            proximos.append(datos)

    datos_partidos = proximos + en_curso + terminados

    return render_template('index.html', datos_partidos=datos_partidos, now=now)


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = 'static/profile_pics'
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Crear nuevo partido (solo si está logueado)




@app.route('/crear', methods=['GET', 'POST'])
@login_required
def crear_partido():
    amigos = current_user.obtener_amigos()

    if request.method == 'POST':
        fecha_str = request.form['fecha']
        hora_str = request.form['hora']
        fecha_hora = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
        solo_por_invitacion = 'solo_por_invitacion' in request.form
        enlace_unico = str(uuid.uuid4()) if not solo_por_invitacion else None

        nuevo_partido = Partido(
            fecha_hora=fecha_hora,
            lugar=request.form['lugar'],
            latitud=float(request.form['latitud']) if request.form['latitud'] else None,
            longitud=float(request.form['longitud']) if request.form['longitud'] else None,
            equipo1=request.form['equipo1'],
            equipo2=request.form['equipo2'],
            max_jugadores=int(request.form['max_jugadores']),
            organizador_id=current_user.id,
            solo_por_invitacion=solo_por_invitacion,
            enlace_invitacion=enlace_unico
        )
        db.session.add(nuevo_partido)
        db.session.commit()

        # Guardar invitaciones
        invitados_ids = request.form.getlist('invitados')
        for uid in invitados_ids:
            invitacion = Invitacion(partido_id=nuevo_partido.id, usuario_id=int(uid))
            db.session.add(invitacion)
        db.session.commit()

        return redirect(url_for('detalle_partido', partido_id=nuevo_partido.id))

    # 👇 aquí es donde pasas la clave a la plantilla
    return render_template(
        'crear_partido.html',
        amigos=amigos,
        google_maps_key=current_app.config['GOOGLE_MAPS_API_KEY']
    )






from flask import session  # ✅ importa esto

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('_flashes', None)  # ✅ limpia mensajes flasheados
    return redirect(url_for('inicio'))

#Ruta para unirse al partido 
@app.route('/partido/<int:partido_id>/unirse', methods=['GET', 'POST'])
@login_required
def unirse_partido(partido_id):
    partido = Partido.query.get_or_404(partido_id)

    if partido.cancelado:
        flash("Este partido fue cancelado. Ya no puedes unirte.", "danger")
        return redirect(url_for('index'))

    inscripcion_existente = Inscripcion.query.filter_by(user_id=current_user.id, partido_id=partido.id).first()
    if inscripcion_existente:
        flash('Ya estás inscrito en este partido.')
        return redirect(url_for('detalle_partido', partido_id=partido.id))

    # Contar jugadores inscritos por equipo
    count_equipo1 = Inscripcion.query.filter_by(partido_id=partido.id, equipo=partido.equipo1).count()
    count_equipo2 = Inscripcion.query.filter_by(partido_id=partido.id, equipo=partido.equipo2).count()

    equipo1_lleno = count_equipo1 >= partido.max_jugadores
    equipo2_lleno = count_equipo2 >= partido.max_jugadores

   
    
    if request.method == 'POST':
        equipo = request.form.get('equipo')
        if equipo not in [partido.equipo1, partido.equipo2]:
            flash('Equipo no válido.')
            return redirect(url_for('unirse_partido', partido_id=partido.id))

        if (equipo == partido.equipo1 and equipo1_lleno) or (equipo == partido.equipo2 and equipo2_lleno):
            flash(f'El equipo {equipo} ya tiene el cupo completo.')
            return redirect(url_for('unirse_partido', partido_id=partido.id))
        
        

        nueva_inscripcion = Inscripcion(user_id=current_user.id, partido_id=partido.id, equipo=equipo)
        db.session.add(nueva_inscripcion)
        db.session.commit()
        flash(f'Te has unido al {equipo} correctamente.')
        return redirect(url_for('detalle_partido', partido_id=partido.id))

    return render_template('unirse_partido.html', partido=partido,
                           count_equipo1=count_equipo1, count_equipo2=count_equipo2,
                           equipo1_lleno=equipo1_lleno, equipo2_lleno=equipo2_lleno)



from models import Amistad, Inscripcion

from models import Invitacion


@app.route('/partido/<int:partido_id>')
@login_required
def detalle_partido(partido_id):
    partido = Partido.query.get_or_404(partido_id)
    calificaciones = list(partido.calificaciones)
    
    
    # Saber si el usuario está inscrito
    ya_inscrito = Inscripcion.query.filter_by(user_id=current_user.id, partido_id=partido.id).first() is not None

    # Verificar si fue invitado
    invitacion = Invitacion.query.filter_by(partido_id=partido.id, usuario_id=current_user.id).first()
    invitado = invitacion is not None

    # Obtener amigos confirmados del organizador (para sección "Invitar Amigos")
    amigos = []
    if current_user.id == partido.organizador_id:
        enviados = [a.amigo for a in current_user.amistades_enviadas if a.confirmada]
        recibidos = [a.usuario for a in current_user.amistades_recibidas if a.confirmada]
        amigos = enviados + recibidos

    # Usuarios ya invitados
    invitados_ids = [inv.usuario_id for inv in partido.invitaciones]

    # Soporte para buscador
    usuarios_buscados = []
    buscar_query = request.args.get("buscar", "").strip()
    if current_user.id == partido.organizador_id and buscar_query:
        usuarios_buscados = User.query.filter(
            User.username.ilike(f"%{buscar_query}%"),
            User.id != current_user.id
        ).all()
         
    
    return render_template(
        'detalle_partido.html',
        partido=partido,
        calificaciones=calificaciones,
        ya_inscrito=ya_inscrito,
        invitado=invitado,
        amigos=amigos,
        invitados_ids=invitados_ids,
        usuarios_buscados=usuarios_buscados,
        google_maps_key=current_app.config['GOOGLE_MAPS_API_KEY']  # 👈 Aquí
        
    )
        

@app.route('/buscar_usuarios_ajax')
@login_required
def buscar_usuarios_ajax():
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify([])

    usuarios = User.query.filter(
        User.username.ilike(f"%{query}%"),
        User.id != current_user.id
    ).all()

    amigos_ids = [u.id for u in current_user.obtener_amigos()]
    solicitudes_enviadas_ids = [a.amigo_id for a in current_user.amistades_enviadas if not a.confirmada]

    resultados = []
    for usuario in usuarios:
        resultados.append({
            'id': usuario.id,
            'username': usuario.username,
            'foto_perfil': usuario.foto_perfil,
            'es_amigo': usuario.id in amigos_ids,
            'ya_enviada': usuario.id in solicitudes_enviadas_ids
        })

    return jsonify(resultados)

from flask import flash  # si quieres mostrar mensajes

@app.route('/rutas')
def rutas():
    rutas = []
    for rule in app.url_map.iter_rules():
        rutas.append(str(rule))
    return "<br>".join(rutas)

from flask import render_template, request, redirect, url_for, flash
from datetime import datetime
from models import db, Partido

@app.route('/partido/<int:partido_id>/editar_resultado', methods=['GET', 'POST'])
@login_required
def editar_resultado(partido_id):
    partido = Partido.query.get_or_404(partido_id)

    if current_user.id != partido.organizador_id:
        abort(403)

    if not partido.resultado:
        flash("Este partido aún no tiene un resultado registrado.", "warning")
        return redirect(url_for('detalle_partido', partido_id=partido_id))

    if request.method == 'POST':
        try:
            goles1 = int(request.form['goles_equipo1'])
            goles2 = int(request.form['goles_equipo2'])
            partido.resultado = f"{goles1}-{goles2}"
            db.session.commit()
            flash("Resultado actualizado correctamente.", "success")
            return redirect(url_for('detalle_partido', partido_id=partido.id))
        except ValueError:
            flash("Ingresa números válidos para los goles.", "danger")

    return render_template('registrar_resultado.html', partido=partido)

@app.route('/partido/<int:partido_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_partido(partido_id):
    partido = Partido.query.get_or_404(partido_id)

    now = datetime.now()

    if partido.cerrado:
        flash("Este partido ya fue cerrado y no puede ser editado.")
        return redirect(url_for('detalle_partido', partido_id=partido_id))

    if partido.fecha_hora <= now:
        flash("El partido ya está en curso o finalizado. No puede ser editado.")
        return redirect(url_for('detalle_partido', partido_id=partido_id))

    if current_user.id != partido.organizador_id:
        abort(403)

    if request.method == 'POST':
        try:
            fecha_str = request.form['fecha']
            hora_str = request.form['hora']
            lugar = request.form['lugar']
            equipo1 = request.form['equipo1']
            equipo2 = request.form['equipo2']
            max_jugadores = int(request.form['max_jugadores'])

            fecha_hora_str = f"{fecha_str} {hora_str}"
            fecha_hora = datetime.strptime(fecha_hora_str, '%Y-%m-%d %H:%M')

            partido.fecha_hora = fecha_hora
            partido.lugar = lugar
            partido.equipo1 = equipo1
            partido.equipo2 = equipo2
            partido.max_jugadores = max_jugadores

            db.session.commit()
            flash('Partido actualizado correctamente.', 'success')
            return redirect(url_for('detalle_partido', partido_id=partido.id))
        except Exception as e:
            flash(f'Error al actualizar el partido: {e}', 'danger')

    return render_template('editar_partido.html', partido=partido)


# Eliminar evento
@app.route('/partido/<int:partido_id>/eliminar', methods=['POST'])
@login_required
def eliminar_partido(partido_id):
    partido = Partido.query.get_or_404(partido_id)

    if current_user.id != partido.organizador_id:
        flash('No tienes permiso para eliminar este partido.', 'error')
        return redirect(url_for('index'))

    # Eliminar invitaciones relacionadas antes de eliminar el partido
    Invitacion.query.filter_by(partido_id=partido.id).delete()

    db.session.delete(partido)
    db.session.commit()
    flash('Partido eliminado correctamente.', 'success')
    return redirect(url_for('index'))


# Puntuar jugadores
@app.route('/partido/<int:partido_id>/calificar/<int:jugador_id>', methods=['GET', 'POST'])
@login_required
def calificar_jugador_individual(partido_id, jugador_id):
    partido = Partido.query.get_or_404(partido_id)
    jugador = User.query.get_or_404(jugador_id)

    # Validaciones:
    if not partido.cerrado:
        flash("El partido aún no está cerrado. No puedes calificar.")
        return redirect(url_for('detalle_partido', partido_id=partido_id))

    inscripcion = Inscripcion.query.filter_by(user_id=current_user.id, partido_id=partido_id).first()
    if not inscripcion:
        flash("Solo los participantes pueden calificar.")
        return redirect(url_for('detalle_partido', partido_id=partido_id))

    calificacion_existente = Calificacion.query.filter_by(
        partido_id=partido_id,
        evaluador_id=current_user.id,
        evaluado_id=jugador_id
    ).first()

    if calificacion_existente:
        flash("Ya has calificado a este jugador.")
        return redirect(url_for('detalle_partido', partido_id=partido_id))

    if request.method == 'POST':
        puntuacion = float(request.form['puntuacion'])
        comentario = request.form.get('comentario', '')

        nueva_calificacion = Calificacion(
            partido_id=partido_id,
            evaluador_id=current_user.id,
            evaluado_id=jugador_id,
            puntuacion=puntuacion,
            comentario=comentario
        )
        db.session.add(nueva_calificacion)
        db.session.commit()

        flash('Calificación registrada con éxito.')
        return redirect(url_for('detalle_partido', partido_id=partido_id))

    # GET: muestra formulario
    return render_template('calificar_jugador.html', jugador=jugador, partido=partido)

from sqlalchemy import func

@app.route('/usuario/<int:user_id>')
@login_required
def perfil_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    calificaciones = list(usuario.calificaciones_recibidas)

    # ✅ Filtrar inscripciones a partidos válidos (no fallidos)
    inscripciones = [
        ins for ins in usuario.inscripciones
        if ins.partido and ins.partido.resultado is not None and not ins.partido.cancelado
    ]

    # Mostrar solicitudes solo si es el propio usuario
    solicitudes = Amistad.query.filter_by(amigo_id=usuario.id, confirmada=False).all() if current_user.id == user_id else []

    # ✅ Invitaciones a partidos solo si es el propio perfil
    invitaciones = Invitacion.query.filter_by(usuario_id=usuario.id).all() if current_user.id == user_id else []

    all_users = User.query.all()

    return render_template(
        'perfil_usuario.html',
        usuario=usuario,
        calificaciones=calificaciones,
        inscripciones=inscripciones,
        solicitudes=solicitudes,
        all_users=all_users,
        invitaciones=invitaciones
    )



def allowed_file(filename):
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in  allowed_extensions

@app.context_processor
def utility_processor():
    def calificacion_jugador_en_partido(jugador, partido_id):
        calificaciones = [c.puntuacion for c in jugador.calificaciones_recibidas if c.partido_id == partido_id]
        if calificaciones:
            return round(sum(calificaciones) / len(calificaciones), 2)
        return None
    return dict(calificacion_jugador_en_partido=calificacion_jugador_en_partido)

@app.context_processor
def inject_notificaciones():
    if current_user.is_authenticated:
        solicitudes = Amistad.query.filter_by(amigo_id=current_user.id, confirmada=False).count()
        invitaciones = Invitacion.query \
            .filter_by(usuario_id=current_user.id) \
            .join(Partido).filter(Partido.cerrado == False).count()
        return {
            'solicitudes_count': solicitudes,
            'invitaciones_count': invitaciones
        }
    return {
        'solicitudes_count': 0,
        'invitaciones_count': 0
    }

from flask import jsonify

@app.route('/subir_foto', methods=['POST'])
@login_required
def subir_foto():
    file = request.files.get('foto_perfil')

    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        timestamp = int(datetime.now().timestamp())
        filename = secure_filename(f"user{current_user.id}_{timestamp}.{ext}")

        upload_folder = app.config.get('UPLOAD_FOLDER', os.path.join(app.root_path, 'static/profile_pics'))
        os.makedirs(upload_folder, exist_ok=True)
        path = os.path.join(upload_folder, filename)

        # Elimina la anterior si no es default
        if current_user.foto_perfil != 'default.jpg':
            old_path = os.path.join(upload_folder, current_user.foto_perfil)
            if os.path.exists(old_path):
                os.remove(old_path)

        file.save(path)
        current_user.foto_perfil = filename
        db.session.commit()

        # ✅ Devuelve JSON para que JS actualice sin redirigir
        return jsonify({
            'filename': filename,
            'timestamp': timestamp
        })

    return jsonify({'error': 'Archivo no válido'}), 400

from datetime import timedelta

@app.route('/partido/<int:partido_id>/registrar_resultado', methods=['GET', 'POST'])
@login_required
def registrar_resultado(partido_id):
    from datetime import timedelta

    partido = Partido.query.get_or_404(partido_id)

    if current_user.id != partido.organizador_id:
        abort(403)

    if partido.cerrado:
        flash("Este partido ya está cerrado.", "warning")
        return redirect(url_for('detalle_partido', partido_id=partido_id))

    # Reglas: 2 horas después del inicio
    tiempo_minimo = partido.fecha_hora + timedelta(hours=1)
    if datetime.now() < tiempo_minimo:
        flash("Debes esperar al menos 1 horas después del inicio del partido para registrar el resultado.", "warning")
        return redirect(url_for('detalle_partido', partido_id=partido_id))

    # Verifica si ambos equipos tienen al menos el 90% de jugadores
    inscripciones = partido.inscripciones
    count_equipo1 = sum(1 for i in inscripciones if i.equipo == partido.equipo1)
    count_equipo2 = sum(1 for i in inscripciones if i.equipo == partido.equipo2)

    umbral = int(round(partido.max_jugadores * 0.7))

    if count_equipo1 < umbral or count_equipo2 < umbral:
        # Partido se cancela
        partido.resultado = None
        partido.cerrado = True
        db.session.commit()
        flash("❌ Partido cancelado por falta de jugadores suficientes en ambos equipos.", "danger")
        return redirect(url_for('detalle_partido', partido_id=partido_id))

    # Si expiró, eliminar
    if partido.esta_expirado():
        db.session.delete(partido)
        db.session.commit()
        flash("Tiempo expirado para registrar el resultado. El partido fue eliminado.", "danger")
        return redirect(url_for('index'))

    # Procesa POST
    if request.method == 'POST':
        try:
            goles1 = int(request.form.get('goles_equipo1'))
            goles2 = int(request.form.get('goles_equipo2'))

            partido.resultado = f"{goles1}-{goles2}"
            partido.cerrado = True

            # Eliminar invitaciones pendientes
            Invitacion.query.filter_by(partido_id=partido.id).delete()

            db.session.commit()
            flash("Resultado registrado y partido cerrado.", "success")
            return redirect(url_for('detalle_partido', partido_id=partido_id))
        except (ValueError, TypeError):
            flash("Ingresa un resultado válido con números.", "danger")

    return render_template('registrar_resultado.html', partido=partido)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    error = None

    if request.method == 'POST':
        form = request.form
        username = form['username']
        password = form['password']

        if User.query.filter_by(username=username).first():
            error = "El nombre de usuario ya existe"
        elif User.query.filter_by(email=form['email']).first():
            error = "Ese correo ya está registrado"
        else:
            token = secrets.token_urlsafe(32)
            nuevo = User(
                username=username,
                password=generate_password_hash(password),
                nombre=form['nombre'],
                apellido=form['apellido'],
                email=form['email'],
                pais=form.get('pais'),
                ciudad=form.get('ciudad'),
                telefono=form.get('telefono'),
                token_confirmacion=token,
                email_confirmado=False
            )
            db.session.add(nuevo)
            db.session.commit()

            try:
                enlace = url_for('confirmar_email', token=token, _external=True)
                mensaje = Message('Confirma tu cuenta en Fútbol App',
                                  recipients=[form['email']],
                                  body=f"Hola {form['nombre']}, confirma tu cuenta aquí:\n{enlace}")
                mail.send(mensaje)
                flash("Revisa tu correo para confirmar tu cuenta.", "info")
            except Exception as e:
                flash(f"Error al enviar correo: {str(e)}", "danger")

            return redirect(url_for('inicio'))

    return render_template('register.html', error=error)


@app.route('/api/verificar-usuario', methods=['POST'])
def verificar_usuario():
    data = request.json
    campo = data.get("campo")
    valor = data.get("valor")

    if campo == "email":
        existe = User.query.filter_by(email=valor).first() is not None
    elif campo == "telefono":
        existe = User.query.filter_by(telefono=valor).first() is not None
    elif campo == "nombre_apellido":
        partes = valor.strip().split(" ", 1)
        if len(partes) == 2:
            nombre, apellido = partes
            existe = User.query.filter_by(nombre=nombre, apellido=apellido).first() is not None
        else:
            existe = False
    else:
        return jsonify({"error": "Campo no válido"}), 400

    return jsonify({"existe": existe})

@app.route('/buscar')
@login_required
def buscar():
    query = request.args.get('q', '')
    resultados = []
    if query:
        resultados = User.query.filter(User.username.ilike(f"%{query}%"), User.id != current_user.id).all()
    return render_template('buscar.html', query=query, resultados=resultados, amistades_enviadas=current_user.amistades_enviadas)

@app.route('/confirmar/<token>')
def confirmar_email(token):
    usuario = User.query.filter_by(token_confirmacion=token).first()
    if usuario:
        usuario.email_confirmado = True
        usuario.token_confirmacion = None
        db.session.commit()
        flash("Tu correo ha sido confirmado. Ya puedes iniciar sesión.", "success")
    else:
        flash("Token inválido o expirado.", "danger")

    return redirect(url_for('inicio'))

@app.route('/agregar_amigo/<int:user_id>', methods=['POST'])
@login_required
def agregar_amigo(user_id):
    if user_id == current_user.id:
        flash("No puedes enviarte solicitud a ti mismo.")
        return redirect(url_for('perfil_usuario', user_id=user_id))

    # Verificar si ya existe una amistad (en cualquier dirección)
    existe = Amistad.query.filter(
        ((Amistad.usuario_id == current_user.id) & (Amistad.amigo_id == user_id)) |
        ((Amistad.usuario_id == user_id) & (Amistad.amigo_id == current_user.id))
    ).first()

    if existe:
        flash("Ya existe una solicitud o ya son amigos.")
    else:
        nueva = Amistad(usuario_id=current_user.id, amigo_id=user_id, confirmada=False)
        db.session.add(nueva)
        db.session.commit()
        flash("Solicitud enviada.")

    return redirect(url_for('perfil_usuario', user_id=user_id))



# Ruta para aceptar amistad
from flask import jsonify, request, abort, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Amistad, Notificacion, User

@app.route('/aceptar_amistad/<int:solicitud_id>', methods=['POST'])
@login_required
def aceptar_amistad(solicitud_id):
    solicitud = Amistad.query.get_or_404(solicitud_id)
    if solicitud.amigo_id != current_user.id:
        abort(403)

    solicitud.confirmada = True
    db.session.commit()

    # Crear notificación para el solicitante
    mensaje = f"{current_user.username} ha aceptado tu solicitud de amistad."
    notificacion = Notificacion(
        tipo='amistad_aceptada',
        mensaje=mensaje,
        usuario_id=solicitud.usuario_id
    )
    db.session.add(notificacion)
    db.session.commit()

    flash("Solicitud aceptada.")
    return redirect(url_for('perfil_usuario', user_id=current_user.id))

@app.route('/notificaciones')
@login_required
def ver_notificaciones():
    notificaciones = Notificacion.query.filter_by(usuario_id=current_user.id).order_by(Notificacion.timestamp.desc()).all()
    return render_template('notificaciones.html', notificaciones=notificaciones)


@app.route('/rechazar_amistad/<int:solicitud_id>', methods=['POST'])
@login_required
def rechazar_amistad(solicitud_id):
    solicitud = Amistad.query.get_or_404(solicitud_id)
    if solicitud.amigo_id != current_user.id:
        abort(403)

    db.session.delete(solicitud)
    db.session.commit()
    flash("Solicitud rechazada.")
    return redirect(url_for('perfil_usuario', user_id=current_user.id))


@app.route('/eliminar_amigo/<int:user_id>', methods=['POST'])
@login_required
def eliminar_amigo(user_id):
    amistad1 = Amistad.query.filter_by(usuario_id=current_user.id, amigo_id=user_id).first()
    amistad2 = Amistad.query.filter_by(usuario_id=user_id, amigo_id=current_user.id).first()

    if amistad1:
        db.session.delete(amistad1)
    if amistad2:
        db.session.delete(amistad2)

    db.session.commit()
    flash('Amistad eliminada.')
    return redirect(url_for('perfil_usuario', user_id=current_user.id))

@app.route('/invitar_usuario/<int:partido_id>/<int:user_id>', methods=['POST'])
@login_required
def invitar_usuario(partido_id, user_id):
    partido = Partido.query.get_or_404(partido_id)

    if current_user.id != partido.organizador_id:
        abort(403)

    # Prevenir duplicados
    ya_invitado = Invitacion.query.filter_by(partido_id=partido_id, usuario_id=user_id).first()
    if ya_invitado:
        return '', 204  # Ya fue invitado

    nueva = Invitacion(partido_id=partido_id, usuario_id=user_id)
    db.session.add(nueva)
    db.session.commit()
    return '', 200


@app.route('/rechazar_invitacion/<int:invitacion_id>', methods=['POST'])
@login_required
def rechazar_invitacion(invitacion_id):
    invitacion = Invitacion.query.get_or_404(invitacion_id)

    if invitacion.usuario_id != current_user.id:
        abort(403)

    db.session.delete(invitacion)
    db.session.commit()
    flash("Invitación rechazada.")
    return redirect(url_for('perfil_usuario', user_id=current_user.id))

@app.route('/aceptar_invitacion/<int:invitacion_id>', methods=['POST'])
@login_required
def aceptar_invitacion(invitacion_id):
    invitacion = Invitacion.query.get_or_404(invitacion_id)

    if invitacion.usuario_id != current_user.id:
        abort(403)

    partido = invitacion.partido

    # Verifica si ya está inscrito
    ya_inscrito = Inscripcion.query.filter_by(user_id=current_user.id, partido_id=partido.id).first()
    if ya_inscrito:
        flash("Ya estás inscrito en este partido.")
        return redirect(url_for('detalle_partido', partido_id=partido.id))

    # Elimina la invitación (se acepta)
    db.session.delete(invitacion)
    db.session.commit()

    # Redirige al formulario para elegir equipo
    return redirect(url_for('unirse_partido', partido_id=partido.id))


@app.route('/partido/<int:partido_id>/buscar_usuarios')
@login_required
def buscar_usuarios_para_invitar(partido_id):
    partido = Partido.query.get_or_404(partido_id)

    # Solo el organizador puede usar esta búsqueda
    if current_user.id != partido.organizador_id or partido.cerrado:
        abort(403)

    query = request.args.get('q', '').strip()
    resultados = []

    if query:
        # Buscar usuarios cuyo username contenga la consulta y que no sean el organizador
        resultados = User.query.filter(
            User.username.ilike(f"%{query}%"),
            User.id != current_user.id
        ).all()

    # Obtener lista de usuarios ya inscritos o invitados
    invitados_ids = [ins.user_id for ins in partido.inscripciones]
    invitados_ids += [inv.usuario_id for inv in partido.invitaciones]

    # Amigos confirmados para mostrarlos aparte
    enviados = [a.amigo for a in current_user.amistades_enviadas if a.confirmada]
    recibidos = [a.usuario for a in current_user.amistades_recibidas if a.confirmada]
    amigos = list({u.id: u for u in enviados + recibidos}.values())

    # Renderiza el mismo template detalle_partido con resultados y control
    calificaciones = list(partido.calificaciones)
    ya_inscrito = Inscripcion.query.filter_by(user_id=current_user.id, partido_id=partido.id).first() is not None

    return render_template(
        'detalle_partido.html',
        partido=partido,
        calificaciones=calificaciones,
        resultados=resultados,
        amigos=amigos,
        invitados_ids=invitados_ids,
        ya_inscrito=ya_inscrito,
        invitado=True  # opcional si usas esta lógica
    )

@app.route('/buscar_usuarios')
@login_required
def buscar_usuarios():
    query = request.args.get('query', '').strip()
    partido_id = request.args.get('partido_id', type=int)

    if not query or not partido_id:
        return jsonify([])

    usuarios = User.query.filter(User.username.ilike(f'%{query}%'), User.id != current_user.id).limit(10).all()

    invitaciones = Invitacion.query.filter_by(partido_id=partido_id).all()
    invitados_ids = {inv.usuario_id for inv in invitaciones}

    resultados = []
    for u in usuarios:
        resultados.append({
            'id': u.id,
            'username': u.username,
            'foto': u.foto_perfil or 'default.jpg',
            'ya_invitado': u.id in invitados_ids
        })

    return jsonify(resultados)

@app.route('/unirse_por_enlace/<string:enlace_invitacion>')
@login_required
def unirse_por_enlace(enlace_invitacion):
    partido = Partido.query.filter_by(enlace_invitacion=enlace_invitacion).first_or_404()

    # ❌ Si fue cancelado
    if partido.cancelado:
        return render_template(
            "partido_bloqueado.html",
            titulo="Partido cancelado",
            mensaje="Este partido fue cancelado. Ya no puedes unirte.",
            partido=partido
        )

    # ❌ Si está en curso
    if partido.esta_en_curso():
        return render_template(
            "partido_bloqueado.html",
            titulo="Partido en curso",
            mensaje="Este partido ya está en curso. Ya no puedes unirte.",
            partido=partido
        )

    # ✅ Si ya está inscrito, mostrar detalle
    ya_inscrito = Inscripcion.query.filter_by(user_id=current_user.id, partido_id=partido.id).first()
    if ya_inscrito:
        flash("Ya estás inscrito en este partido.")
        return redirect(url_for('detalle_partido', partido_id=partido.id))

    # ✅ Si está cerrado, no permitir
    if partido.cerrado:
        flash("El partido ya fue cerrado.")
        return redirect(url_for('detalle_partido', partido_id=partido.id))

    # ✅ Redirige al formulario de inscripción normal
    return redirect(url_for('unirse_partido', partido_id=partido.id))
@app.route('/ajax/aceptar_invitacion/<int:invitacion_id>', methods=['POST'])
@login_required
def ajax_aceptar_invitacion(invitacion_id):
    invitacion = Invitacion.query.get_or_404(invitacion_id)

    if invitacion.usuario_id != current_user.id:
        return jsonify({'success': False}), 403

    partido_id = invitacion.partido_id

    # Elimina la invitación al aceptarla
    db.session.delete(invitacion)
    db.session.commit()

    # Devuelve la URL para que el usuario elija el equipo
    return jsonify({
        'success': True,
        'redirect_url': url_for('unirse_partido', partido_id=partido_id)
    })



@app.route('/ajax/rechazar_invitacion/<int:invitacion_id>', methods=['POST'])
@login_required
def ajax_rechazar_invitacion(invitacion_id):
    invitacion = Invitacion.query.get_or_404(invitacion_id)
    if invitacion.usuario_id != current_user.id:
        return jsonify({'success': False}), 403

    db.session.delete(invitacion)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/ajax/aceptar_amistad/<int:solicitud_id>', methods=['POST'])
@login_required
def ajax_aceptar_amistad(solicitud_id):
    solicitud = Amistad.query.get_or_404(solicitud_id)
    if solicitud.amigo_id != current_user.id:
        return jsonify({'success': False}), 403

    solicitud.confirmada = True
    db.session.commit()

    notificacion = Notificacion(
        tipo='amistad_aceptada',
        mensaje=f"{current_user.username} aceptó tu solicitud de amistad.",
        usuario_id=solicitud.usuario_id
    )
    db.session.add(notificacion)
    db.session.commit()

    return jsonify({'success': True})


@app.route('/ajax/rechazar_amistad/<int:solicitud_id>', methods=['POST'])
@login_required
def ajax_rechazar_amistad(solicitud_id):
    solicitud = Amistad.query.get_or_404(solicitud_id)
    if solicitud.amigo_id != current_user.id:
        return jsonify({'success': False}), 403

    db.session.delete(solicitud)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/hora-local')
def hora_local():
    return f"Hora local detectada por Flask: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# Crear las tablas si no existen
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
