"""Área administrativa: CRUD de regiões monitoradas (RF09). Todas as rotas exigem JWT.

Uma região criada aqui com `collect = true` entra no próximo ciclo da coleta sem mudar código
(RNF05), e como a pertença dos focos é espacial, ela já "enxerga" o histórico gravado.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ignis.api.auth import require_admin
from ignis.api.schemas import BBox
from ignis.db.models import Region, RegionKind
from ignis.db.seed import bbox_to_multipolygon
from ignis.db.session import get_session

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class RegionCreate(BBox):
    slug: str = Field(min_length=2, max_length=64, pattern=SLUG_PATTERN)
    name: str = Field(min_length=2, max_length=120)
    collect: bool = True


class RegionUpdate(BaseModel):
    """Campos opcionais; o bbox só muda se vier completo."""

    name: str | None = Field(None, min_length=2, max_length=120)
    bbox: BBox | None = None
    collect: bool | None = None
    active: bool | None = None


def _as_dict(region: Region) -> dict:
    return {
        "slug": region.slug,
        "name": region.name,
        "kind": region.kind.value,
        "collect": region.collect,
        "active": region.active,
        "bbox": {"west": region.west, "south": region.south, "east": region.east, "north": region.north},
        "created_at": region.created_at.isoformat() if region.created_at else None,
        "updated_at": region.updated_at.isoformat() if region.updated_at else None,
    }


def _bbox_geom(bbox: BBox):
    geometry = bbox_to_multipolygon(bbox.west, bbox.south, bbox.east, bbox.north)
    return func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326)


def _get_or_404(session: Session, slug: str) -> Region:
    region = session.scalar(select(Region).where(Region.slug == slug))
    if region is None:
        raise HTTPException(status_code=404, detail=f"região '{slug}' não encontrada")
    return region


@router.get("/regions")
def list_regions(session: Session = Depends(get_session)) -> list[dict]:
    """Todas as regiões, inclusive as desativadas."""
    regions = session.scalars(select(Region).order_by(Region.kind.desc(), Region.id))
    return [_as_dict(r) for r in regions]


@router.post("/regions", status_code=status.HTTP_201_CREATED)
def create_region(body: RegionCreate, session: Session = Depends(get_session)) -> dict:
    """Cadastra uma área de monitoramento por bounding box."""
    if session.scalar(select(Region.id).where(Region.slug == body.slug)) is not None:
        raise HTTPException(status_code=409, detail=f"já existe uma região com slug '{body.slug}'")
    region = Region(
        slug=body.slug,
        name=body.name,
        kind=RegionKind.MONITORING,
        west=body.west,
        south=body.south,
        east=body.east,
        north=body.north,
        geom=_bbox_geom(body),
        collect=body.collect,
        active=True,
    )
    session.add(region)
    session.commit()
    session.refresh(region)
    return _as_dict(region)


@router.patch("/regions/{slug}")
def update_region(slug: str, body: RegionUpdate, session: Session = Depends(get_session)) -> dict:
    region = _get_or_404(session, slug)
    if body.bbox is not None:
        if region.kind == RegionKind.COUNTRY:
            # o contorno do país vem do Natural Earth (seed); trocar por retângulo perderia a fronteira
            raise HTTPException(
                status_code=422, detail="região de país usa polígono de fronteira: o bbox não é editável"
            )
        region.west, region.south = body.bbox.west, body.bbox.south
        region.east, region.north = body.bbox.east, body.bbox.north
        region.geom = _bbox_geom(body.bbox)
    if body.name is not None:
        region.name = body.name
    if body.collect is not None:
        region.collect = body.collect
    if body.active is not None:
        region.active = body.active
    session.commit()
    session.refresh(region)
    return _as_dict(region)


@router.delete("/regions/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_region(slug: str, session: Session = Depends(get_session)) -> Response:
    """Desativa a região (some do portal e da coleta). Não apaga a linha: leituras de FWI,
    regras de alerta e boletins ligados a ela continuam consultáveis, e o PATCH reativa."""
    region = _get_or_404(session, slug)
    region.active = False
    region.collect = False
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
