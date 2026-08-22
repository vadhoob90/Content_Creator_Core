"""Provide runner capabilities."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from pydantic import ValidationError

from .configuration import Configuration
from .context_composition import (
    ContextCompositionStore,
    ContextInvocation,
    ContextInvocationIdentity,
    invocation_record,
)
from .diagnostics import RuntimeDiagnostics
from .domain import ModelRequest, ModelResponse
from .prompt_provenance import PromptComposition
from .prompting import PromptAssembler
from .providers import ProviderRegistry
from .runner_models import AgentRunOptions as AgentRunOptions

ContextTraceSink = Callable[[ContextInvocation], None]


class AgentOutputError(ValueError):
    """Report agent output failures."""

    pass


class AgentRunner:
    """Execute repository-owned agent roles through a provider."""

    def __init__(
        self,
        configuration: Configuration,
        registry: ProviderRegistry,
        prompts: PromptAssembler,
        diagnostics: Optional[RuntimeDiagnostics] = None,
    ):
        """Initialize the agent runner with its required state and collaborators.

        Args:
            configuration (Configuration): The active repository configuration.
            registry (ProviderRegistry): The registry used to resolve and persist domain
                entries.
            prompts (PromptAssembler): The prompts value passed to init.
            diagnostics (Optional[RuntimeDiagnostics]): The runtime diagnostics service used
                to record safe evidence. Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.configuration = configuration
        self.registry = registry
        self.prompts = prompts
        self.diagnostics = diagnostics
        self.history: list[ModelRequest] = []
        self.responses: list[Optional[ModelResponse]] = []
        self.context_store = ContextCompositionStore(prompts.root)
        self.pending_context: list[ContextInvocation] = []
        self.context_trace_sink: Optional[ContextTraceSink] = None

    def enable_context_trace(self, sink: ContextTraceSink) -> None:
        """Configure privacy-safe live composition evidence delivery.

        Args:
            sink (ContextTraceSink): Entry-point callback receiving structured evidence.

        Returns:
            None: Subsequent invocation provenance is delivered to the callback.
        """
        self.context_trace_sink = sink

    def bind_context_run(self, run_id: str) -> None:
        """Bind and flush relevant pre-run composition.

        Args:
            run_id (str): Stable persisted content run identifier.

        Returns:
            None: Pending evidence is persisted into the new run.
        """
        for invocation in self.pending_context:
            self.context_store.append(run_id, invocation)
        self.pending_context.clear()

    def run(
        self,
        role: str,
        role_key: str,
        instruction: str,
        payload: Dict[str, Any],
        options: Optional[AgentRunOptions] = None,
    ) -> Any:
        """Run the agent runner workflow.

        Args:
            role (str): The repository-owned agent role to execute.
            role_key (str): The role key text processed when run.
            instruction (str): The instruction text processed when run.
            payload (Dict[str, Any]): The structured payload to validate or persist.
            options (Optional[AgentRunOptions]): The options controlling this operation.
                Defaults to ``None``.

        Returns:
            Any: The execution value for value.

        Raises:
            AgentOutputError: If the agent output operation cannot complete.
        """
        resolved_options = options or AgentRunOptions()
        request, composition = self._prepared_request(
            role, role_key, instruction, payload, resolved_options
        )
        self._record_context(
            role,
            role_key,
            instruction,
            payload,
            resolved_options,
            request,
            composition,
        )
        policy = self.configuration.diagnostic_policy
        max_attempts = policy["max_attempts"] if self.diagnostics and policy["enabled"] else 1
        for attempt in range(1, max_attempts + 1):
            result = self._attempt(request, role, attempt, max_attempts, resolved_options)
            if result is not None:
                return result
        raise AgentOutputError(f"{role} exhausted its attempts")

    def _request(
        self,
        role: str,
        role_key: str,
        instruction: str,
        payload: Dict[str, Any],
        options: AgentRunOptions,
    ) -> ModelRequest:
        """Return the request.

        Args:
            role (str): The repository-owned agent role to execute.
            role_key (str): The role key text processed when request.
            instruction (str): The instruction text processed when request.
            payload (Dict[str, Any]): The structured payload to validate or persist.
            options (AgentRunOptions): The options controlling this operation.

        Returns:
            ModelRequest: The resulting model request for request.
        """
        return self._prepared_request(role, role_key, instruction, payload, options)[0]

    def _prepared_request(
        self,
        role: str,
        role_key: str,
        instruction: str,
        payload: Dict[str, Any],
        options: AgentRunOptions,
    ) -> tuple[ModelRequest, PromptComposition]:
        """Build one exact request together with instruction provenance.

        Args:
            role (str): Repository-owned agent role.
            role_key (str): Model-selection role key.
            instruction (str): Private task instruction.
            payload (Dict[str, Any]): Private structured task payload.
            options (AgentRunOptions): Invocation options.

        Returns:
            tuple[ModelRequest, PromptComposition]: Exact request and composition evidence.
        """
        required = set(options.tools)
        if options.output_model:
            required.add("structured_output")
        selection = self.configuration.selection(
            role_key,
            provider=options.provider,
            profile=options.profile,
            required_capabilities=required,
        )
        composition = self.prompts.compose(role, options.order)
        request = ModelRequest(
            role=role,
            system=composition.prompt,
            user=self.prompts.user_prompt(instruction, payload),
            selection=selection,
            max_output_tokens=self.configuration.max_output_tokens,
            output_schema=(
                options.output_model.model_json_schema() if options.output_model else None
            ),
            tools=options.tools,
        )
        return request, composition

    def _record_context(
        self,
        role: str,
        role_key: str,
        instruction: str,
        payload: Dict[str, Any],
        options: AgentRunOptions,
        request: ModelRequest,
        composition: PromptComposition,
    ) -> None:
        """Persist or queue privacy-safe provenance before provider execution.

        Args:
            role (str): Repository-owned agent role.
            role_key (str): Model-selection role key.
            instruction (str): Private task instruction.
            payload (Dict[str, Any]): Private structured task payload.
            options (AgentRunOptions): Invocation options.
            request (ModelRequest): Exact provider request.
            composition (PromptComposition): Exact system-prompt provenance.

        Returns:
            None: Evidence is displayed, queued, or persisted in place.
        """
        run_id = options.run_id or (self.diagnostics.run_id if self.diagnostics else None)
        payload_sources = options.payload_sources or self._payload_sources(
            run_id, options.phase or role_key, payload
        )
        invocation = invocation_record(
            identity=ContextInvocationIdentity(
                role=role,
                role_key=role_key,
                phase=options.phase or role_key,
                provider=request.selection.provider,
                model=request.selection.model,
            ),
            layers=composition.layers,
            instruction=instruction,
            payload=payload,
            payload_sources=payload_sources,
        )
        if self.context_trace_sink:
            self.context_trace_sink(invocation)
        if run_id:
            self.context_store.append(run_id, invocation)
        else:
            self.pending_context.append(invocation)

    @staticmethod
    def _payload_sources(run_id: Optional[str], phase: str, payload: Dict[str, Any]) -> list[str]:
        """Return exact run artifacts represented in a private task payload.

        Args:
            run_id (Optional[str]): Bound persisted run identifier, when available.
            phase (str): Human-readable lifecycle phase.
            payload (Dict[str, Any]): Private structured task payload.

        Returns:
            list[str]: Existing or imminent run-local artifact locators.
        """
        if not run_id:
            return []
        root = f"runs/{run_id}/"
        sources = [root + "work-order.json"] if "work_order" in payload else []
        if payload.get("research") is not None:
            sources.append(root + "research.json")
        if payload.get("draft") is not None:
            suffix = phase.removeprefix("critique-")
            sources.append(root + (f"draft-{suffix}.md" if suffix != phase else "final.md"))
        if payload.get("assessment") is not None:
            sources.append(root + "assessment.json")
        return sources

    def _attempt(
        self,
        request: ModelRequest,
        role: str,
        attempt: int,
        max_attempts: int,
        options: AgentRunOptions,
    ) -> Any:
        """Return the attempt.

        Args:
            request (ModelRequest): The validated request that initiates the operation.
            role (str): The repository-owned agent role to execute.
            attempt (int): The one-based execution attempt number.
            max_attempts (int): The max attempts value that controls attempt.
            options (AgentRunOptions): The options controlling this operation.

        Returns:
            Any: The resulting value for attempt.
        """
        self.history.append(request)
        response_index = len(self.responses)
        self.responses.append(None)
        started_at = self.diagnostics.timer() if self.diagnostics else 0.0
        if self.diagnostics:
            self.diagnostics.attempt_started(
                role=role,
                attempt=attempt,
                provider=request.selection.provider,
                model=request.selection.model,
            )
        try:
            response = self.registry.get(request.selection.provider).generate(request)
            self.responses[response_index] = response
            result = self._parse_response(response.text, role, options)
        except Exception as error:
            if self._record_failure(error, request, role, attempt, max_attempts, started_at):
                return None
            raise
        if self.diagnostics:
            self.diagnostics.attempt_completed(
                role=role,
                attempt=attempt,
                provider=request.selection.provider,
                model=request.selection.model,
                started_at=started_at,
            )
        return result

    @staticmethod
    def _parse_response(response_text: str, role: str, options: AgentRunOptions) -> Any:
        """Parse the response.

        Args:
            response_text (str): The response text text processed when parse response.
            role (str): The repository-owned agent role to execute.
            options (AgentRunOptions): The options controlling this operation.

        Returns:
            Any: The parsed value for response.

        Raises:
            AgentOutputError: If the agent output operation cannot complete.
        """
        if not options.output_model:
            return response_text.strip()
        try:
            return options.output_model.model_validate(json.loads(response_text))
        except (json.JSONDecodeError, ValidationError) as error:
            raise AgentOutputError(f"{role} returned invalid structured output: {error}") from error

    def _record_failure(
        self,
        error: Exception,
        request: ModelRequest,
        role: str,
        attempt: int,
        max_attempts: int,
        started_at: float,
    ) -> bool:
        """Record the failure.

        Args:
            error (Exception): The error value passed to record failure.
            request (ModelRequest): The validated request that initiates the operation.
            role (str): The repository-owned agent role to execute.
            attempt (int): The one-based execution attempt number.
            max_attempts (int): The max attempts value that controls record failure.
            started_at (float): The started at value that controls record failure.

        Returns:
            bool: Whether record failure satisfies the documented condition.
        """
        retrying = bool(
            self.diagnostics and attempt < max_attempts and self.diagnostics.is_retryable(error)
        )
        if self.diagnostics:
            self.diagnostics.attempt_failed(
                error,
                role=role,
                attempt=attempt,
                provider=request.selection.provider,
                model=request.selection.model,
                started_at=started_at,
                retrying=retrying,
            )
        return retrying
