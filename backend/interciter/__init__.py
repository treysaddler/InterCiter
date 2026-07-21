"""InterCiter MVP backend.

A thin, auditable vertical slice of the InterCiter design: ingest an open-access
biomedical paper (JATS XML), anchor empirical result claims to their exact source
passages, classify each cited relationship (function + stance) with calibrated
abstention, and trace one hop to the cited paper or a confidently matched target
claim.

The rich, immutable logical model is the system of record (``interciter.models``);
reads go through a derived, rebuildable projection (``interciter.services.projection``).
"""

__version__ = "0.1.0"
