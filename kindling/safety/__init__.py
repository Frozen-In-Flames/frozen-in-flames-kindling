"""Consent, provenance, privacy, and safety (Part 19)."""

from .consent import (ConsentVerificationError, RevocationRegistry,
                      verify_consent)
from .governance import (DataGovernance, MisuseMonitor, UserDataManager,
                         legal_policy, openness_statement)
from .watermark import (detect_watermark, embed_watermark, sign_provenance,
                        survival_report, verify_provenance)

__all__ = [
    "verify_consent", "ConsentVerificationError", "RevocationRegistry",
    "embed_watermark", "detect_watermark",
    "sign_provenance", "verify_provenance", "survival_report",
    "DataGovernance", "UserDataManager", "MisuseMonitor",
    "openness_statement", "legal_policy",
]
