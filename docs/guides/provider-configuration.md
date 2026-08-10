# Provider configuration

The orchestrator requests a role and capability profile. It never names a
vendor model. `config/models.yaml` maps each provider's `fast`, `balanced`, and
`deep` profiles to ordered candidates.

Selection is deterministic:

1. Use the work-order provider, shell override, or explicit workspace default
2. Resolve the role to a profile
3. Filter candidates by required capabilities such as `structured_output` and
   `web_search`
4. Choose the first remaining candidate
5. Fail closed when no candidate is capable

This makes two models of the same type an explicit policy choice rather than an
unexplained model judgement. Reorder candidates only after replay and live
evaluations support the change.

Complexity comes from the route, not an LLM improvising model names. Briefing and
learning use `fast`; light research and ordinary drafting/review use
`balanced`; deep research and a deep-research article's drafting/review use
`deep`. A no-research article therefore does not automatically pay for the
deepest model.

Two execution modes receive the same normalized request.

### Native mode (preferred)

- `codex-native` invokes `codex exec` using an existing ChatGPT login
- `claude-native` invokes `claude -p` using an existing Claude subscription login

Use native mode for normal local and interactive work. It avoids separate API
credentials and consumes the relevant product subscription allowance.

### API mode

- `openai` uses the Responses API
- `anthropic` uses the Messages API

Use API mode for CI, headless automation, explicit metering, or service-account
operation. Provider-specific structured-output and search syntax remains inside
`src/content_creator/providers/`.

API credentials come from `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. Do not place
credentials in YAML. Core deliberately ships without a provider default.

For Anthropic models deployed through Microsoft Foundry, use the Foundry-specific
SDK configuration:

```bash
export ANTHROPIC_FOUNDRY_RESOURCE=<foundry-resource-name>
export ANTHROPIC_FOUNDRY_API_KEY=<foundry-api-key>
```

Alternatively, set `ANTHROPIC_FOUNDRY_BASE_URL` to the complete Foundry Anthropic
endpoint. Core also recognizes a canonical
`https://<resource>.services.ai.azure.com/anthropic` endpoint supplied through
`ANTHROPIC_BASE_URL` and accepts `ANTHROPIC_API_KEY` as its compatibility key.
Foundry model values are deployment names rather than public Anthropic model IDs;
place a reviewed complete model catalogue at workspace `config/models.yaml` when
the packaged candidates do not match the deployed names.

Persist a deliberate workspace choice:

```bash
content-creator provider select codex-native
```

This writes `provider.default` to `content-creator.yaml`. Alternatively, pass
`--provider` for one command or set `CONTENT_CREATOR_PROVIDER` to `openai`,
`anthropic`, `codex-native`, or `claude-native` for a temporary shell override.
If none is supplied, Core exits cleanly rather than choosing a potentially
metered provider.

Native modes deliberately remove API-key variables from their child processes
and fail unless the CLI reports subscription-backed authentication. This
prevents a native run silently falling back to API billing.

Each researcher, writer, critic, voice analyst, profile critic, evaluator, or
learning-extractor call starts an isolated, non-interactive CLI session. The
deterministic Python orchestrator still owns routing, persistence, voice and
perspective isolation, validation, revision limits, checkpoints, publication,
and learning.

Codex CLI strict structured output is used when a contract fits OpenAI's strict
JSON Schema subset. Contracts containing open-ended mappings are supplied as
schema instructions and validated by the existing downstream Pydantic
contract. Invalid output still fails closed.

The Anthropic adapter applies the SDK's supported schema transformation before
using grammar mode. Open-ended mappings and schemas above Anthropic's documented
optional-parameter or union-parameter limits use schema-in-prompt JSON instead,
with the same downstream Pydantic validation. If Anthropic rejects a smaller
schema because of an internal grammar limit or compilation timeout, Core makes
one bounded prompt-JSON retry. Other provider failures are not retried by this
fallback.

### Native setup

For Codex:

```bash
codex login
content-creator provider select codex-native
content-creator provider verify codex-native
```

For Claude Code:

```bash
claude auth login
content-creator provider select claude-native
content-creator provider verify claude-native
```

Choose a Claude subscription login, not `claude auth login --console`.

The committed OpenAI tiers follow the current GPT-5.6 family: Luna for fast,
Terra for balanced, and Sol for deep work. The Anthropic tiers use Claude Haiku
4.5, Sonnet 5, and Opus 5. Verify availability for the account before a live
run. Native Claude profiles use the CLI's `haiku`, `sonnet`, and `opus`
aliases. Model IDs and capabilities are checked against the providers'
official guidance:

- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [Anthropic models overview](https://platform.claude.com/docs/en/about-claude/models/overview)

To add another provider:

1. Implement the `Provider` interface
2. Register it in `ProviderRegistry`
3. Add profiles to `config/models.yaml`
4. Run the shared adapter and route tests
5. Add a manual live evaluation before treating it as production-ready

The complete executable example in
[`examples/extensions/custom_provider.py`](../../examples/extensions/custom_provider.py)
implements `Provider.generate`, registers the adapter, creates a normalized
`ModelRequest`, and verifies the normalized `ModelResponse`. Keep authentication,
vendor payloads, retries, and response conversion inside the adapter; the
orchestrator should receive only Core contracts.
