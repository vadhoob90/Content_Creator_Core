# Provider configuration

The orchestrator requests a role and capability profile. It never names a
vendor model. `config/models.yaml` maps each provider's `fast`, `balanced`, and
`deep` profiles to ordered candidates.

Selection is deterministic:

1. Use the work-order provider or the configured default
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
credentials in YAML. Set `CONTENT_CREATOR_PROVIDER` to `openai`, `anthropic`,
`codex-native`, or `claude-native` to choose the default for the current shell
without editing the catalogue.

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

### Native setup

For Codex:

```bash
codex login
content-creator provider verify codex-native
```

For Claude Code:

```bash
claude auth login
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
