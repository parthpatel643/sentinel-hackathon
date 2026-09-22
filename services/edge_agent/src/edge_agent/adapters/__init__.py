"""Federation adapters: sources this platform can pull camera feeds from."""

from edge_agent.adapters.gov_catalogue import CatalogueEntryError, GovCatalogueClient

__all__ = ["CatalogueEntryError", "GovCatalogueClient"]
