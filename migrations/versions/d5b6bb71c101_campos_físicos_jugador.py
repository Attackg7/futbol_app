"""Campos físicos jugador

Revision ID: d5b6bb71c101
Revises: 
Create Date: 2025-07-04 22:08:25.045435

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5b6bb71c101'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('_alembic_tmp_calificacion')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('posicion', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('edad', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('peso', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('altura', sa.Float(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('altura')
        batch_op.drop_column('peso')
        batch_op.drop_column('edad')
        batch_op.drop_column('posicion')

    op.create_table('_alembic_tmp_calificacion',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('partido_id', sa.INTEGER(), nullable=False),
    sa.Column('evaluador_id', sa.INTEGER(), nullable=False),
    sa.Column('evaluado_id', sa.INTEGER(), nullable=False),
    sa.Column('puntuacion', sa.FLOAT(), nullable=False),
    sa.Column('comentario', sa.TEXT(), nullable=True),
    sa.Column('fecha', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['evaluado_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['evaluador_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['partido_id'], ['partido.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partido_id', 'evaluador_id', 'evaluado_id', name=op.f('unique_calificacion'))
    )
    # ### end Alembic commands ###
