"""Local catalogue access; no network calls or itinerary generation."""

from .catalog import Catalog, CatalogError, CatalogSelection, load_catalog

__all__ = ["Catalog", "CatalogError", "CatalogSelection", "load_catalog"]
