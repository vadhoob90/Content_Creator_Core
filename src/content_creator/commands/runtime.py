"""Implement the runtime command family.

Parser composition, dispatch, and specialist command families live in focused
modules. This module owns only public compatibility exports and error-to-exit-code
handling.
"""

from __future__ import annotations

from typing import List, Optional

from ..configuration import ConfigurationError
from ..diagnostics import DiagnosticDecisionRequired
from ..orchestrator import OrchestrationError, Orchestrator
from ..packs import PackError
from ..providers import ProviderError
from ..publication_lifecycle import PublicationReviewRequired
from ..publication_provenance import PublicationProvenanceError
from ..runner import AgentOutputError
from ..storage import StorageError
from ..upgrade import WorkspaceUpgradeError
from ..voice_ml import MLDependencyError
from . import dispatch
from .parser import build_parser as build_parser
from .shared import print_json


def main(argv: Optional[List[str]] = None) -> int:
    """Run the command-line interface and return its exit status.

    Args:
        argv (Optional[List[str]]): The command-line argument sequence. Defaults to
            ``None``.

    Returns:
        int: The process exit status, where zero indicates successful handling.
    """
    try:
        setattr(dispatch, "Orchestrator", Orchestrator)  # noqa: B010
        return dispatch.run(argv)
    except DiagnosticDecisionRequired as exc:
        print_json(exc.preflight)
        return 4
    except PublicationReviewRequired as exc:
        print_json(exc.report)
        return 4
    except (
        AgentOutputError,
        ConfigurationError,
        OrchestrationError,
        PackError,
        ProviderError,
        PublicationProvenanceError,
        MLDependencyError,
        StorageError,
        WorkspaceUpgradeError,
    ) as exc:
        result = {
            "status": "error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        diagnostic_path = getattr(exc, "diagnostic_path", None)
        if diagnostic_path:
            result["diagnostic_summary"] = diagnostic_path
        print_json(result)
        return 8


def _main(argv: Optional[List[str]] = None) -> int:
    """Run the runtime command-line entry point.

    Args:
        argv (Optional[List[str]]): The command-line argument sequence. Defaults to
            ``None``.

    Returns:
        int: The resulting numeric value for main.
    """
    setattr(dispatch, "Orchestrator", Orchestrator)  # noqa: B010
    return dispatch.run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
