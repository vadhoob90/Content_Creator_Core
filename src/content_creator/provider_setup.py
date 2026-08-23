"""Provide verified provider readiness for the first-run journey."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .configuration import persist_default_provider
from .coordinator_models import CoordinatorAction
from .providers import ProviderRegistry
from .storage import RunStore

VERIFICATION_PATH = Path(".content-creator/provider-verification.json")
USAGE_BILLED_PROVIDERS = {"anthropic", "bedrock", "openai"}


def verify_and_select_provider(
    root: Path,
    provider_name: str,
    *,
    confirm_api_billing: bool,
) -> tuple[int, dict[str, Any]]:
    """Verify one explicit provider choice before persisting it.

    Args:
        root (Path): Author workspace root.
        provider_name (str): Registered provider selected by the author.
        confirm_api_billing (bool): Whether usage billing was explicitly accepted.

    Returns:
        tuple[int, dict[str, Any]]: Exit status and privacy-safe result.
    """
    if provider_name in USAGE_BILLED_PROVIDERS and not confirm_api_billing:
        return 8, {
            "status": "confirmation-required",
            "provider": provider_name,
            "message": "Confirm this usage-billed provider with --confirm-api-billing.",
        }
    authentication = ProviderRegistry(root=root).get(provider_name).verify()
    path = persist_default_provider(root, provider_name)
    record_provider_verification(root, provider_name, authentication)
    return 0, {
        "status": "verified",
        "provider": provider_name,
        "persisted_to": str(path),
        **authentication,
    }


def record_provider_verification(
    root: Path,
    provider_name: str,
    authentication: dict[str, Any],
) -> Path:
    """Persist a privacy-safe local verification receipt.

    Args:
        root (Path): Author workspace root.
        provider_name (str): Provider that passed verification.
        authentication (dict[str, Any]): Adapter verification metadata.

    Returns:
        Path: Local ignored verification receipt path.
    """
    path = root.resolve() / VERIFICATION_PATH
    payload = {
        "schema_version": "1.0",
        "provider": provider_name,
        "status": "verified",
        "verified_at": datetime.now(UTC).isoformat(),
        "authentication": authentication,
    }
    RunStore._atomic_text(path, json.dumps(payload, indent=2, default=str))
    return path


def provider_verification_is_current(root: Path, provider_name: str) -> bool:
    """Return whether the selected provider has a successful local receipt.

    Args:
        root (Path): Author workspace root.
        provider_name (str): Currently selected provider.

    Returns:
        bool: Whether a matching successful receipt is available.
    """
    path = root.resolve() / VERIFICATION_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return payload.get("provider") == provider_name and payload.get("status") == "verified"


def provider_choices() -> list[CoordinatorAction]:
    """Return viable provider confirmations without silently selecting one.

    Returns:
        list[CoordinatorAction]: Available or configured provider actions.
    """
    choices = []
    for name, executable in (("codex-native", "codex"), ("claude-native", "claude")):
        if shutil.which(executable):
            choices.append(_provider_action(name, "subscription"))
    for name, variable in (("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")):
        if os.getenv(variable):
            choices.append(_provider_action(name, "usage billed", confirm=True))
    if _bedrock_credentials_available():
        choices.append(_provider_action("bedrock", "usage billed", confirm=True))
    return choices


def _provider_action(name: str, billing: str, *, confirm: bool = False) -> CoordinatorAction:
    """Return one explicit provider action.

    Args:
        name (str): Registered provider name.
        billing (str): Concise billing mode label.
        confirm (bool): Whether billing confirmation is required. Defaults to ``False``.

    Returns:
        CoordinatorAction: Explicit verify-and-select action.
    """
    command = ["setup", "provider", name]
    if confirm:
        command.append("--confirm-api-billing")
    return CoordinatorAction(
        id=f"connect-{name}",
        label=f"{name} ({billing})",
        command=command,
        mutates_workspace=True,
        requires_confirmation=True,
    )


def _bedrock_credentials_available() -> bool:
    """Return whether the AWS credential chain has a visible entry point.

    Returns:
        bool: Whether a supported AWS credential hint is present.
    """
    return bool(
        os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        or os.getenv("AWS_PROFILE")
        or (os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"))
        or os.getenv("AWS_WEB_IDENTITY_TOKEN_FILE")
        or os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
    )
