"""Read-only external capability discovery. Catalog entries are never executable grants."""
from .public_apis import CatalogEntry, parse_public_apis, parse_public_apis_category

__all__ = ["CatalogEntry", "parse_public_apis", "parse_public_apis_category"]
