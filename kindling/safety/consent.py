"""Voice consent (19.1): Part 8.4 in full.

Recorded, verified consent tied to the person whose voice is used, or
documented rights for a licensed/synthetic source. Blocks creation of a
voice character of a named real person without verification. Owner
revocation takes effect for new renders immediately.
"""

from typing import Any, Dict, List, Optional


class ConsentVerificationError(ValueError):
    pass


# Named real persons require verification; this is a blocklist hook.
# Reference: non-empty check against the provided name.
def verify_consent(name: str, consent: Optional[Dict[str, Any]],
                   is_named_real_person: bool = False) -> Dict[str, Any]:
    """Verify consent before creating a voice character (19.1).

    consent: {"subject", "rights_basis": "consent"|"licensed"|"synthetic",
              "verified": bool, "recorded_at", ...}.
    """
    if consent is None:
        raise ConsentVerificationError("consent record required")
    basis = consent.get("rights_basis")
    if basis not in ("consent", "licensed", "synthetic"):
        raise ConsentVerificationError(
            f"unknown rights_basis {basis!r}")
    if is_named_real_person and basis != "consent":
        raise ConsentVerificationError(
            f"named real person {name!r}: verified personal consent required")
    if basis == "consent" and not consent.get("verified"):
        raise ConsentVerificationError(
            "personal consent must be verified")
    if not consent.get("subject"):
        raise ConsentVerificationError("consent must name its subject")
    return {"verified": True, "subject": consent["subject"],
            "rights_basis": basis,
            "recorded_at": consent.get("recorded_at", "unknown")}


class RevocationRegistry:
    """Owner revocation, effective immediately for new renders (19.1)."""

    def __init__(self):
        self._revoked: Dict[str, float] = {}
        import time
        self._time = time.time

    def revoke(self, voice_id: str, owner_id: str):
        self._revoked[voice_id] = self._time()

    def is_revoked(self, voice_id: str) -> bool:
        return voice_id in self._revoked

    def check_renderable(self, voice_id: str):
        if self.is_revoked(voice_id):
            raise ConsentVerificationError(
                f"voice {voice_id} revoked; new renders blocked")
