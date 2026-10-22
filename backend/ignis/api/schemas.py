"""Modelos de entrada compartilhados entre as rotas públicas e as de admin."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, model_validator


class BBox(BaseModel):
    """Retângulo em graus (WGS 84), no formato da Area API da FIRMS: oeste, sul, leste, norte."""

    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        # bbox que cruza o antimeridiano (oeste > leste) não é aceito pela FIRMS num pedido só
        if self.west >= self.east:
            raise ValueError("oeste deve ser menor que leste")
        if self.south >= self.north:
            raise ValueError("sul deve ser menor que norte")
        return self

    @classmethod
    def parse(cls, text: str) -> BBox:
        """Lê "oeste,sul,leste,norte" (como na FIRMS)."""
        parts = text.split(",")
        if len(parts) != 4:
            raise ValueError("bbox deve ter 4 números: oeste,sul,leste,norte")
        west, south, east, north = (float(p) for p in parts)
        return cls(west=west, south=south, east=east, north=north)
