"""fwi: escala oficial do EFFIS, máximo e nº de pixels por região

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21 23:00:00

A escala do EFFIS não tem "muito baixo" e tem "muito extremo" (FWI >= 70, desde 06/2021);
ver docs/fonte-fwi.md. A tabela ainda não tinha leituras quando esta migration foi criada,
então as colunas novas entram como NOT NULL sem default.
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('fwi_readings', sa.Column('fwi_max', sa.Float(), nullable=False))
    op.add_column('fwi_readings', sa.Column('pixel_count', sa.Integer(), nullable=False))
    op.create_check_constraint(
        'ck_fwi_readings_danger_class',
        'fwi_readings',
        "danger_class IN ('low', 'moderate', 'high', 'very_high', 'extreme', 'very_extreme')",
    )
    op.create_check_constraint('ck_fwi_readings_pixel_count', 'fwi_readings', 'pixel_count > 0')


def downgrade() -> None:
    op.execute("DELETE FROM fwi_readings WHERE danger_class = 'very_extreme'")
    op.drop_constraint('ck_fwi_readings_pixel_count', 'fwi_readings', type_='check')
    op.drop_constraint('ck_fwi_readings_danger_class', 'fwi_readings', type_='check')
    op.drop_column('fwi_readings', 'pixel_count')
    op.drop_column('fwi_readings', 'fwi_max')
