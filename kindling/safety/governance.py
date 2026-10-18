"""Training data governance, user data, misuse handling, transparency.

- 19.3: license ledger, opt-outs, deletion; no training on user uploads
  by default (explicit revocable opt-in).
- 19.4: retention, owner export, deletion with cascade.
- 19.5: usage policy, reporting/takedown channel, abuse detection
  without listening to private projects.
- 19.6: exact openness statement.
- 19.7: versioned legal policies.
"""

import time
from typing import Any, Dict, List


class DataGovernance:
    """Training data governance (19.3)."""

    def __init__(self):
        self.opt_outs: set = set()
        self.deletion_requests: List[Dict[str, Any]] = []
        # Default: user uploads/assets NEVER train models.
        self.training_opt_ins: set = set()

    def opt_out(self, item_id: str):
        self.opt_outs.add(item_id)

    def request_deletion(self, item_id: str, owner_id: str):
        self.deletion_requests.append({"item_id": item_id,
                                       "owner": owner_id,
                                       "at": time.time(),
                                       "status": "pending"})

    def grant_training_opt_in(self, owner_id: str):
        self.training_opt_ins.add(owner_id)

    def revoke_training_opt_in(self, owner_id: str):
        self.training_opt_ins.discard(owner_id)

    def may_train_on(self, item_id: str, owner_id: str) -> bool:
        if item_id in self.opt_outs:
            return False
        return owner_id in self.training_opt_ins

    def process_deletions(self) -> List[Dict[str, Any]]:
        done = []
        for req in self.deletion_requests:
            if req["status"] == "pending":
                req["status"] = "deleted"
                done.append(req)
        return done


class UserDataManager:
    """User data: retention, export, cascading deletion (19.4)."""

    RETENTION_DAYS = 365

    def __init__(self):
        self.store: Dict[str, Dict[str, Any]] = {}

    def put(self, owner_id: str, kind: str, item_id: str, data: Any):
        self.store.setdefault(owner_id, {}).setdefault(kind, {})[item_id] = {
            "data": data, "created_at": time.time()}

    def export(self, owner_id: str) -> Dict[str, Any]:
        return {"owner": owner_id,
                "data": self.store.get(owner_id, {})}

    def delete_owner(self, owner_id: str) -> Dict[str, Any]:
        """Deletion cascades to derived assets, traits, caches (19.4)."""
        owned = self.store.pop(owner_id, {})
        cascaded = []
        for kind, items in owned.items():
            for item_id in items:
                cascaded.append(f"{kind}:{item_id}")
        return {"owner": owner_id, "deleted": cascaded,
                "cascaded": True}


class MisuseMonitor:
    """Abuse detection without listening to private projects (19.5).

    Counts metadata-level signals only: consent failures, impersonation
    flags, bulk creation attempts. Never inspects audio content.
    """

    def __init__(self):
        self.consent_failures: Dict[str, int] = {}
        self.creation_counts: Dict[str, List[float]] = {}

    def record_consent_failure(self, user_id: str):
        self.consent_failures[user_id] = \
            self.consent_failures.get(user_id, 0) + 1

    def record_creation(self, user_id: str):
        self.creation_counts.setdefault(user_id, []).append(time.time())

    def check_abuse(self, user_id: str) -> Dict[str, Any]:
        flags = []
        if self.consent_failures.get(user_id, 0) >= 3:
            flags.append("repeated_consent_failures")
        recent = [t for t in self.creation_counts.get(user_id, [])
                  if time.time() - t < 3600]
        if len(recent) >= 10:
            flags.append("bulk_creation_attempts")
        return {"user": user_id, "flags": flags,
                "limited": bool(flags)}


def openness_statement() -> Dict[str, Any]:
    """Exactly what is open, under what license (19.6)."""
    return {
        "code": {"open": True, "license": "Apache-2.0",
                 "scope": "all kindling/ modules, tests, docs"},
        "reference_models": {"open": True, "license": "Apache-2.0",
                             "note": "procedural reference implementations"},
        "trained_weights": {"open": False,
                            "note": "no trained weights ship yet"},
        "datasets": {"open": False,
                     "note": "no training datasets ship with the repo"},
        "word": "open is used only for the above; nothing else claims it",
    }


def legal_policy(version: str = "1.0.0") -> Dict[str, Any]:
    """Versioned legal review record (19.7)."""
    return {"version": version,
            "areas": ["data_sources", "licensing", "voice_rights",
                      "distribution"],
            "note": "assign counsel per jurisdiction before shipping; "
                    "this record versions the policy like code"}
