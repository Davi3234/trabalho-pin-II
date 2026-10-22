"""Modelo de dados do IGNIS (SQLAlchemy 2 + GeoAlchemy2).

Decisões que importam para os requisitos:
- Focos NÃO têm FK de região: a pertença é calculada com ST_Intersects, então um foco
  em regiões sobrepostas é gravado uma vez e uma região nova "enxerga" o histórico (RNF05).
- Dedup natural (source, latitude, longitude, acq_date, acq_time) com coordenadas numeric,
  para comparação exata em INSERT ... ON CONFLICT DO NOTHING (RF02).
- alert_events é append-only, garantido por trigger na migration (RF10).
- subscribers guarda só o mínimo exigido pela LGPD/GDPR (RNF04).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ignis.interpretation.models import Confidence


class Base(DeclarativeBase):
    pass


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    # VARCHAR + CHECK em vez de ENUM nativo: adicionar valores não exige migration de tipo
    return Enum(cls, name=name, native_enum=False, values_callable=lambda e: [m.value for m in e], length=20)


class RegionKind(str, enum.Enum):
    MONITORING = "monitoring"  # área de coleta (bbox enviado à FIRMS)
    COUNTRY = "country"  # sub-região para ranking e alertas (polígono de fronteira)


class RunStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class DangerClass(str, enum.Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"
    EXTREME = "extreme"


class AlertMetric(str, enum.Enum):
    COUNT = "count"
    FRP_SUM = "frp_sum"
    FRP_MAX = "frp_max"


class SubscriberStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    UNSUBSCRIBED = "unsubscribed"


class ReportKind(str, enum.Enum):
    ON_DEMAND = "on_demand"
    DAILY_BULLETIN = "daily_bulletin"


class ReportGenerator(str, enum.Enum):
    LLM = "llm"
    TEMPLATE = "template"


class Region(Base):
    __tablename__ = "regions"
    __table_args__ = (
        CheckConstraint("west < east AND south < north", name="ck_regions_bbox_order"),
        CheckConstraint(
            "west >= -180 AND east <= 180 AND south >= -90 AND north <= 90", name="ck_regions_bbox_range"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[RegionKind] = mapped_column(_enum(RegionKind, "region_kind"))
    west: Mapped[float] = mapped_column(Float)
    south: Mapped[float] = mapped_column(Float)
    east: Mapped[float] = mapped_column(Float)
    north: Mapped[float] = mapped_column(Float)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False)
    collect: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def bbox_str(self) -> str:
        """Formato aceito pela Area API da FIRMS: oeste,sul,leste,norte."""
        return f"{self.west:g},{self.south:g},{self.east:g},{self.north:g}"


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job: Mapped[str] = mapped_column(String(20))  # "firms" | "fwi"
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"), default=RunStatus.RUNNING)
    fetched_rows: Mapped[int] = mapped_column(Integer, default=0)
    new_detections: Mapped[int] = mapped_column(Integer, default=0)
    transactions_used: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)  # resultado por região x sensor, erros
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_collection_runs_job_started", "job", "started_at"),)


class FireDetection(Base):
    __tablename__ = "fire_detections"
    __table_args__ = (
        UniqueConstraint(
            "source", "latitude", "longitude", "acq_date", "acq_time", name="uq_fire_detections_natural"
        ),
        Index("ix_fire_detections_acquired_at", "acquired_at"),
        Index("ix_fire_detections_source_acquired_at", "source", "acquired_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # VIIRS_NOAA20_NRT, VIIRS_SNPP_NRT, MODIS_NRT
    latitude: Mapped[Decimal] = mapped_column(Numeric(8, 5))
    longitude: Mapped[Decimal] = mapped_column(Numeric(8, 5))
    acq_date: Mapped[date] = mapped_column(Date)
    acq_time: Mapped[int] = mapped_column(SmallInteger)  # HHMM em UTC, como vem da FIRMS
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    satellite: Mapped[str | None] = mapped_column(String(16))
    confidence: Mapped[Confidence] = mapped_column(_enum(Confidence, "confidence_level"))
    confidence_raw: Mapped[str] = mapped_column(String(8))
    frp: Mapped[float | None] = mapped_column(Float)
    brightness: Mapped[float | None] = mapped_column(Float)
    scan: Mapped[float | None] = mapped_column(Float)
    track: Mapped[float | None] = mapped_column(Float)
    daynight: Mapped[str | None] = mapped_column(String(1))
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=True), nullable=False)
    first_run_id: Mapped[int | None] = mapped_column(ForeignKey("collection_runs.id", ondelete="SET NULL"))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FwiReading(Base):
    __tablename__ = "fwi_readings"
    __table_args__ = (UniqueConstraint("region_id", "date", "provider", name="uq_fwi_region_date_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    fwi_value: Mapped[float] = mapped_column(Float)
    danger_class: Mapped[DangerClass] = mapped_column(_enum(DangerClass, "danger_class"))
    provider: Mapped[str] = mapped_column(String(40))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    region: Mapped[Region] = relationship()


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint("threshold > 0", name="ck_alert_rules_threshold"),
        CheckConstraint("window_hours > 0 AND cooldown_hours >= 0", name="ck_alert_rules_windows"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    metric: Mapped[AlertMetric] = mapped_column(_enum(AlertMetric, "alert_metric"))
    threshold: Mapped[float] = mapped_column(Float)
    window_hours: Mapped[int] = mapped_column(Integer, default=24)
    min_confidence: Mapped[Confidence | None] = mapped_column(_enum(Confidence, "confidence_level"))
    cooldown_hours: Mapped[int] = mapped_column(Integer, default=12)
    notify_subscribers: Mapped[bool] = mapped_column(Boolean, default=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    region: Mapped[Region] = relationship()


class AlertEvent(Base):
    """Append-only (trigger trg_alert_events_append_only). Sem FK para regra/região de
    propósito: o registro de auditoria sobrevive à exclusão da regra (o snapshot guarda o contexto)."""

    __tablename__ = "alert_events"
    __table_args__ = (Index("ix_alert_events_rule_triggered", "rule_id", "triggered_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int] = mapped_column(Integer)
    region_id: Mapped[int] = mapped_column(Integer)
    rule_snapshot: Mapped[dict] = mapped_column(JSONB)
    measured_value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # apenas IDs de assinantes e status de entrega — nunca e-mails em claro (RNF04)
    recipients: Mapped[dict] = mapped_column(JSONB, default=dict)


class Subscriber(Base):
    __tablename__ = "subscribers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    status: Mapped[SubscriberStatus] = mapped_column(
        _enum(SubscriberStatus, "subscriber_status"), default=SubscriberStatus.PENDING
    )
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consent_terms_version: Mapped[str] = mapped_column(String(20))
    confirm_token_hash: Mapped[str | None] = mapped_column(String(64))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    regions: Mapped[list[Region]] = relationship(secondary="subscriber_regions")


class SubscriberRegion(Base):
    __tablename__ = "subscriber_regions"

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True
    )
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"), primary_key=True)


class AiReport(Base):
    __tablename__ = "ai_reports"
    __table_args__ = (Index("ix_ai_reports_input_hash", "input_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[ReportKind] = mapped_column(_enum(ReportKind, "report_kind"))
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id", ondelete="SET NULL"))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_json: Mapped[dict] = mapped_column(JSONB)
    input_hash: Mapped[str] = mapped_column(String(64))  # sha256 do input -> reaproveitar sem nova chamada
    output_text: Mapped[str] = mapped_column(Text)
    generator: Mapped[ReportGenerator] = mapped_column(_enum(ReportGenerator, "report_generator"))
    model: Mapped[str | None] = mapped_column(String(80))
    validation: Mapped[dict] = mapped_column(JSONB, default=dict)
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Bulletin(Base):
    __tablename__ = "bulletins"
    __table_args__ = (UniqueConstraint("date", "region_id", name="uq_bulletins_date_region"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"))
    report_id: Mapped[int] = mapped_column(ForeignKey("ai_reports.id", ondelete="RESTRICT"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    report: Mapped[AiReport] = relationship()
