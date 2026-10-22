"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-21 20:57:24.347994
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION ignis_forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'tabela % é append-only (auditoria RF10)', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table('alert_events',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=False),
    sa.Column('region_id', sa.Integer(), nullable=False),
    sa.Column('rule_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('measured_value', sa.Float(), nullable=False),
    sa.Column('threshold', sa.Float(), nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('window_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('recipients', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alert_events_rule_triggered', 'alert_events', ['rule_id', 'triggered_at'], unique=False)
    op.create_table('collection_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Enum('running', 'success', 'partial', 'failed', name='run_status', native_enum=False, length=20), nullable=False),
    sa.Column('fetched_rows', sa.Integer(), nullable=False),
    sa.Column('new_detections', sa.Integer(), nullable=False),
    sa.Column('transactions_used', sa.Integer(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_collection_runs_job_started', 'collection_runs', ['job', 'started_at'], unique=False)
    op.create_table('regions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.Enum('monitoring', 'country', name='region_kind', native_enum=False, length=20), nullable=False),
    sa.Column('west', sa.Float(), nullable=False),
    sa.Column('south', sa.Float(), nullable=False),
    sa.Column('east', sa.Float(), nullable=False),
    sa.Column('north', sa.Float(), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', nullable=False, spatial_index=False), nullable=False),
    sa.Column('collect', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('west < east AND south < north', name='ck_regions_bbox_order'),
    sa.CheckConstraint('west >= -180 AND east <= 180 AND south >= -90 AND north <= 90', name='ck_regions_bbox_range'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index('idx_regions_geom', 'regions', ['geom'], unique=False, postgresql_using='gist')
    op.create_table('subscribers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('status', sa.Enum('pending', 'confirmed', 'unsubscribed', name='subscriber_status', native_enum=False, length=20), nullable=False),
    sa.Column('consent_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consent_terms_version', sa.String(length=20), nullable=False),
    sa.Column('confirm_token_hash', sa.String(length=64), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('ai_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('on_demand', 'daily_bulletin', name='report_kind', native_enum=False, length=20), nullable=False),
    sa.Column('region_id', sa.Integer(), nullable=True),
    sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('input_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('input_hash', sa.String(length=64), nullable=False),
    sa.Column('output_text', sa.Text(), nullable=False),
    sa.Column('generator', sa.Enum('llm', 'template', name='report_generator', native_enum=False, length=20), nullable=False),
    sa.Column('model', sa.String(length=80), nullable=True),
    sa.Column('validation', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('usage', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ai_reports_input_hash', 'ai_reports', ['input_hash'], unique=False)
    op.create_table('alert_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('region_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('metric', sa.Enum('count', 'frp_sum', 'frp_max', name='alert_metric', native_enum=False, length=20), nullable=False),
    sa.Column('threshold', sa.Float(), nullable=False),
    sa.Column('window_hours', sa.Integer(), nullable=False),
    sa.Column('min_confidence', sa.Enum('low', 'nominal', 'high', 'unknown', name='confidence_level', native_enum=False, length=20), nullable=True),
    sa.Column('cooldown_hours', sa.Integer(), nullable=False),
    sa.Column('notify_subscribers', sa.Boolean(), nullable=False),
    sa.Column('webhook_url', sa.String(length=500), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('threshold > 0', name='ck_alert_rules_threshold'),
    sa.CheckConstraint('window_hours > 0 AND cooldown_hours >= 0', name='ck_alert_rules_windows'),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('fire_detections',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('latitude', sa.Numeric(precision=8, scale=5), nullable=False),
    sa.Column('longitude', sa.Numeric(precision=8, scale=5), nullable=False),
    sa.Column('acq_date', sa.Date(), nullable=False),
    sa.Column('acq_time', sa.SmallInteger(), nullable=False),
    sa.Column('acquired_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('satellite', sa.String(length=16), nullable=True),
    sa.Column('confidence', sa.Enum('low', 'nominal', 'high', 'unknown', name='confidence_level', native_enum=False, length=20), nullable=False),
    sa.Column('confidence_raw', sa.String(length=8), nullable=False),
    sa.Column('frp', sa.Float(), nullable=True),
    sa.Column('brightness', sa.Float(), nullable=True),
    sa.Column('scan', sa.Float(), nullable=True),
    sa.Column('track', sa.Float(), nullable=True),
    sa.Column('daynight', sa.String(length=1), nullable=True),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', nullable=False, spatial_index=False), nullable=False),
    sa.Column('first_run_id', sa.Integer(), nullable=True),
    sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['first_run_id'], ['collection_runs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'latitude', 'longitude', 'acq_date', 'acq_time', name='uq_fire_detections_natural')
    )
    op.create_index('idx_fire_detections_geom', 'fire_detections', ['geom'], unique=False, postgresql_using='gist')
    op.create_index('ix_fire_detections_acquired_at', 'fire_detections', ['acquired_at'], unique=False)
    op.create_index('ix_fire_detections_source_acquired_at', 'fire_detections', ['source', 'acquired_at'], unique=False)
    op.create_table('fwi_readings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('region_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('fwi_value', sa.Float(), nullable=False),
    sa.Column('danger_class', sa.Enum('very_low', 'low', 'moderate', 'high', 'very_high', 'extreme', name='danger_class', native_enum=False, length=20), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('region_id', 'date', 'provider', name='uq_fwi_region_date_provider')
    )
    op.create_table('subscriber_regions',
    sa.Column('subscriber_id', sa.UUID(), nullable=False),
    sa.Column('region_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subscriber_id'], ['subscribers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('subscriber_id', 'region_id')
    )
    op.create_table('bulletins',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('region_id', sa.Integer(), nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['ai_reports.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('date', 'region_id', name='uq_bulletins_date_region')
    )

    op.execute(APPEND_ONLY_FN)
    op.execute(
        "CREATE TRIGGER trg_alert_events_append_only BEFORE UPDATE OR DELETE ON alert_events "
        "FOR EACH ROW EXECUTE FUNCTION ignis_forbid_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_alert_events_append_only ON alert_events")
    op.execute("DROP FUNCTION IF EXISTS ignis_forbid_mutation()")
    op.drop_table('bulletins')
    op.drop_table('subscriber_regions')
    op.drop_table('fwi_readings')
    op.drop_index('ix_fire_detections_source_acquired_at', table_name='fire_detections')
    op.drop_index('ix_fire_detections_acquired_at', table_name='fire_detections')
    op.drop_index('idx_fire_detections_geom', table_name='fire_detections', postgresql_using='gist')
    op.drop_table('fire_detections')
    op.drop_table('alert_rules')
    op.drop_index('ix_ai_reports_input_hash', table_name='ai_reports')
    op.drop_table('ai_reports')
    op.drop_table('subscribers')
    op.drop_index('idx_regions_geom', table_name='regions', postgresql_using='gist')
    op.drop_table('regions')
    op.drop_index('ix_collection_runs_job_started', table_name='collection_runs')
    op.drop_table('collection_runs')
    op.drop_index('ix_alert_events_rule_triggered', table_name='alert_events')
    op.drop_table('alert_events')
