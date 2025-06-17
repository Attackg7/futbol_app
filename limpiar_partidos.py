# limpiar_partidos.py
from app import db, app
from models import Partido
from datetime import datetime, timedelta

with app.app_context():
    expirados = Partido.query.filter(
        Partido.cerrado == False,
        Partido.fecha_hora + timedelta(hours=12) < datetime.utcnow()
    ).all()

    for partido in expirados:
        db.session.delete(partido)

    db.session.commit()
    print(f"{len(expirados)} partidos expirados eliminados.")
