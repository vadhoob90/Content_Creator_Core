"""Voice CLI parser registration."""

from __future__ import annotations

import argparse

from .shared import PROVIDERS


def register(sub: argparse._SubParsersAction) -> None:
    voice = sub.add_parser("voice", help=argparse.SUPPRESS)
    voice_sub = voice.add_subparsers(dest="voice_command", required=True)
    voice_onboard = voice_sub.add_parser(
        "onboard",
        help="Choose a starter or source-derived voice route",
    )
    voice_onboard.add_argument("voice_id")
    voice_onboard.add_argument(
        "--strategy",
        choices=["starter", "source-derived"],
        required=True,
    )
    voice_onboard.add_argument("--author-name", required=True)
    voice_onboard.add_argument("--label")
    voice_onboard.add_argument(
        "--selected-by",
        default="repository-owner",
        help="Person making the onboarding choice",
    )
    voice_onboard.add_argument("--use", action="append", default=[])
    voice_onboard.add_argument(
        "--statistical-voice-score",
        choices=["disabled", "deterministic", "ml"],
        default="disabled",
        help="Voice-scoped score preference selected during onboarding",
    )
    voice_create = voice_sub.add_parser("create")
    voice_create.add_argument(
        "--name",
        help="Legacy shorthand for author name, display label, and generated id",
    )
    voice_create.add_argument("--voice-id", help="Stable local voice identifier")
    voice_create.add_argument("--label", help="Human-facing voice label")
    voice_create.add_argument(
        "--author-name",
        help="Author/byline identity used for attribution",
    )
    voice_create.add_argument(
        "--author-alias",
        action="append",
        default=[],
        help="Additional authorised byline or transcript identity",
    )
    voice_create.add_argument("--authorised-by")
    voice_create.add_argument("--use", action="append", default=[])
    voice_create.add_argument("--sources")
    voice_create.add_argument("--documents", action="append", default=[])
    voice_create.add_argument("--no-build", action="store_true")
    voice_create.add_argument("--provider", choices=PROVIDERS)
    voice_create.add_argument(
        "--statistical-voice-score",
        choices=["disabled", "deterministic", "ml"],
        default="disabled",
        help="Voice-scoped score preference selected during creation",
    )
    voice_create.add_argument(
        "--offline-analysis",
        action="store_true",
        help="Use deterministic fixture analysis instead of an LLM",
    )
    for command in ("build", "rebuild", "status", "show", "signature", "verify"):
        item = voice_sub.add_parser(command)
        item.add_argument("voice_id")
        if command in {"build", "rebuild"}:
            item.add_argument("--provider", choices=PROVIDERS)
            item.add_argument("--offline-analysis", action="store_true")
    voice_assess = voice_sub.add_parser(
        "assess",
        help="Compare a draft with an active voice's linguistic distribution",
    )
    voice_assess.add_argument("voice_id")
    voice_assess.add_argument("--draft", required=True)
    voice_assess.add_argument("--voice-version")
    voice_score = voice_sub.add_parser(
        "score",
        help="Compute a statistical voice score for one draft",
    )
    voice_score.add_argument("voice_id")
    voice_score.add_argument("--draft", required=True)
    voice_score.add_argument("--voice-version")
    voice_score.add_argument(
        "--method",
        choices=["deterministic", "ml"],
        required=True,
    )
    voice_score_config = voice_sub.add_parser(
        "score-config",
        help="Change automatic statistical voice scoring for one voice",
    )
    voice_score_config.add_argument("voice_id")
    voice_score_config.add_argument(
        "--method",
        choices=["deterministic", "ml"],
    )
    score_config_state = voice_score_config.add_mutually_exclusive_group(required=True)
    score_config_state.add_argument("--enable", action="store_true")
    score_config_state.add_argument("--disable", action="store_true")
    voice_score_config.add_argument("--selected-by")
    voice_train_ml = voice_sub.add_parser(
        "train-ml",
        help="Explicitly train an optional author-versus-comparison voice model",
    )
    voice_train_ml.add_argument("voice_id")
    voice_train_ml.add_argument("--voice-version")
    voice_train_ml.add_argument(
        "--comparison-documents",
        action="append",
        required=True,
        help="Matched non-author file or directory; repeat for several",
    )
    voice_train_ml.add_argument(
        "--accept-low-confidence",
        action="store_true",
        help="Train after explicitly accepting preflight reliability warnings",
    )
    voice_train_ml.add_argument(
        "--replace",
        action="store_true",
        help="Replace the model for the resolved immutable voice version",
    )
    voice_sub.add_parser("list")
    voice_sub.add_parser(
        "verify-all",
        help="Verify every candidate and active voice in the workspace",
    )
    voice_approve = voice_sub.add_parser("approve")
    voice_approve.add_argument("voice_id")
    voice_approve.add_argument("--approved-by", default="repository-owner")
    voice_approve.add_argument("--override-evaluation", action="store_true")
    voice_approve.add_argument("--reason")
    voice_deactivate = voice_sub.add_parser("deactivate")
    voice_deactivate.add_argument("voice_id")
    voice_deactivate.add_argument("--reason", required=True)
    voice_reactivate = voice_sub.add_parser("reactivate")
    voice_reactivate.add_argument("voice_id")
    voice_reactivate.add_argument("--approved-by", default="repository-owner")
    voice_add = voice_sub.add_parser("add-sources")
    voice_add.add_argument("voice_id")
    voice_add.add_argument("--sources")
    voice_add.add_argument("--documents", action="append", default=[])
    voice_diff = voice_sub.add_parser("diff")
    voice_diff.add_argument("voice_id")
    voice_diff.add_argument("--from", dest="from_version", required=True)
    voice_diff.add_argument("--to", dest="to_version", required=True)
    voice_consolidate = voice_sub.add_parser("consolidate-learnings")
    voice_consolidate.add_argument("voice_id")
