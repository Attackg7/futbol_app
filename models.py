from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
from uuid import uuid4


db = SQLAlchemy()

from sqlalchemy.orm import validates

class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    foto_perfil = db.Column(db.String(120), default='logoMATCHES.png')
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    pais = db.Column(db.String(100))
    ciudad = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    email_confirmado = db.Column(db.Boolean, default=False)
    token_confirmacion = db.Column(db.String(100), nullable=True)

    calificaciones_recibidas = db.relationship(
        'Calificacion', foreign_keys='Calificacion.evaluado_id',
        back_populates='evaluado', lazy='dynamic'
    )
    calificaciones_realizadas = db.relationship(
        'Calificacion', foreign_keys='Calificacion.evaluador_id',
        back_populates='evaluador', lazy='dynamic'
    )
    inscripciones = db.relationship('Inscripcion', back_populates='user', lazy='dynamic')
    partidos_creados = db.relationship('Partido', back_populates='organizador', lazy='dynamic')

    amistades_enviadas = db.relationship('Amistad',
                                         foreign_keys='Amistad.usuario_id',
                                         backref='solicitante', lazy='dynamic')
    amistades_recibidas = db.relationship('Amistad',
                                          foreign_keys='Amistad.amigo_id',
                                          backref='receptor', lazy='dynamic')

    @validates('foto_perfil')
    def validate_foto_perfil(self, key, value):
        return value or 'default.jpg'

    def promedio_calificaciones(self):
        calificaciones = self.calificaciones_recibidas.all()
        if not calificaciones:
            return "Sin calificaciones"
        promedio = sum(c.puntuacion for c in calificaciones) / len(calificaciones)
        return round(promedio, 1)

    def promedio_en_partido(self, partido_id):
        calificaciones = [
            c.puntuacion for c in self.calificaciones_recibidas if c.partido_id == partido_id
        ]
        if calificaciones:
            return round(sum(calificaciones) / len(calificaciones), 2)
        return None

    def obtener_amigos(self):
        """Devuelve una lista de usuarios con los que tienes amistad confirmada."""
        amigos_confirmados = []

        for amistad in self.amistades_enviadas:
            if amistad.confirmada:
                amigos_confirmados.append(amistad.amigo)
        for amistad in self.amistades_recibidas:
            if amistad.confirmada:
                amigos_confirmados.append(amistad.usuario)
        return amigos_confirmados


class Partido(db.Model):
    __tablename__ = 'partido'

    id = db.Column(db.Integer, primary_key=True)
    fecha_hora = db.Column(db.DateTime, nullable=False)
    lugar = db.Column(db.String(200), nullable=False)
    equipo1 = db.Column(db.String(100), nullable=False)
    equipo2 = db.Column(db.String(100), nullable=False)
    max_jugadores = db.Column(db.Integer, nullable=False)
    resultado = db.Column(db.String(100))
    cerrado = db.Column(db.Boolean, default=False)
    solo_por_invitacion = db.Column(db.Boolean, default=False)
    enlace_invitacion = db.Column(db.String(100), unique=True, nullable=True)  # ✅ Link público
    cancelado = db.Column(db.Boolean, default=False)
    foto_perfil = db.Column(db.String(120), nullable=False, default='default.jpg')
    latitud = db.Column(db.Float)
    longitud = db.Column(db.Float)

    organizador_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    organizador = db.relationship('User', back_populates='partidos_creados')

    inscripciones = db.relationship('Inscripcion', back_populates='partido', cascade="all, delete-orphan")
    calificaciones = db.relationship('Calificacion', backref='partido', lazy='dynamic', cascade="all, delete-orphan")

    def tiempo_limite(self):
        return self.fecha_hora + timedelta(hours=12)

    def esta_expirado(self):
        return datetime.now() > self.tiempo_limite() and not self.cerrado

    def generar_enlace_unico(self):
        """Genera un enlace de invitación si aún no existe"""
        if not self.enlace_invitacion:
            self.enlace_invitacion = str(uuid4())
    
    def esta_en_curso(self):
        ahora =  datetime.now()
        duracion = timedelta(hours=2)  # Ajusta si tu partido dura más
        return self.fecha_hora <= ahora <= self.fecha_hora + duracion
    
    def equipo_ganador(self):
        if not self.resultado:
            return None
        try:
            goles = [int(g.strip()) for g in self.resultado.split('-')]
            if len(goles) != 2:
                return None
            if goles[0] > goles[1]:
                return self.equipo1
            elif goles[1] > goles[0]:
                return self.equipo2
            return None  # Empate
        except (ValueError, IndexError):
            return None
        

class Inscripcion(db.Model):
    __tablename__ = 'inscripcion'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    partido_id = db.Column(db.Integer, db.ForeignKey('partido.id'))
    equipo = db.Column(db.String(100))

    user = db.relationship('User', back_populates='inscripciones')
    partido = db.relationship('Partido', back_populates='inscripciones')


class Calificacion(db.Model):
    __tablename__ = 'calificacion'

    id = db.Column(db.Integer, primary_key=True)
    partido_id = db.Column(db.Integer, db.ForeignKey('partido.id'), nullable=False)
    evaluador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    evaluado_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    puntuacion = db.Column(db.Float, nullable=False)
    comentario = db.Column(db.Text, nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('partido_id', 'evaluador_id', 'evaluado_id', name='unique_calificacion'),
    )

    evaluador = db.relationship('User', foreign_keys=[evaluador_id], back_populates='calificaciones_realizadas')
    evaluado = db.relationship('User', foreign_keys=[evaluado_id], back_populates='calificaciones_recibidas')


class Amistad(db.Model):
    __tablename__ = 'amistad'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amigo_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    confirmada = db.Column(db.Boolean, default=False)

    usuario = db.relationship('User', foreign_keys=[usuario_id], back_populates='amistades_enviadas')
    amigo = db.relationship('User', foreign_keys=[amigo_id], back_populates='amistades_recibidas')

    __table_args__ = (
        db.UniqueConstraint('usuario_id', 'amigo_id', name='unique_amistad'),
    )

class Invitacion(db.Model):
    __tablename__ = 'invitacion'
    id = db.Column(db.Integer, primary_key=True)
    partido_id = db.Column(db.Integer, db.ForeignKey('partido.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    partido = db.relationship('Partido', backref='invitaciones')
    usuario = db.relationship('User', backref='invitaciones_recibidas')

    __table_args__ = (
        db.UniqueConstraint('partido_id', 'usuario_id', name='unique_invitacion'),
    )

class Notificacion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(50))  # Por ejemplo: 'amistad_aceptada'
    mensaje = db.Column(db.String(255))
    leido = db.Column(db.Boolean, default=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Receptor
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    usuario = db.relationship('User', backref='notificaciones')
