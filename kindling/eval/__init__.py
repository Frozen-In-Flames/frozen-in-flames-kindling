"""Evaluation program (Part 17)."""

from .automatic import (check_audio_quality, check_edit_locality,
                        check_identity_similarity,
                        check_reproducibility_declared, check_tempo_key)
from .program import (HUMAN_PROTOCOL, check_release_gates, datasheet,
                      inter_rater_agreement, model_card, reliability_report)
from .suite import (REFRESH_SCHEDULE, SUITE_VERSION, build_held_out,
                    build_suite, suite_ids)
from .transfer import (transfer_asset_stability,
                       transfer_instrument_new_passages,
                       transfer_preset_new_song, transfer_voice_new_lyrics)

__all__ = [
    "build_suite", "build_held_out", "suite_ids",
    "SUITE_VERSION", "REFRESH_SCHEDULE",
    "check_tempo_key", "check_audio_quality", "check_identity_similarity",
    "check_edit_locality", "check_reproducibility_declared",
    "transfer_voice_new_lyrics", "transfer_preset_new_song",
    "transfer_instrument_new_passages", "transfer_asset_stability",
    "reliability_report", "HUMAN_PROTOCOL", "inter_rater_agreement",
    "model_card", "datasheet", "check_release_gates",
]
