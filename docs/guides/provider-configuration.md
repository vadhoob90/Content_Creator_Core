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

OpenAI uses the Responses API. Anthropic uses the Messages API. Both adapters
receive the same normalized request. Provider-specific structured-output and
search syntax remains inside `src/content_creator/providers/`.

Credentials come from `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. Do not place
credentials in YAML.

To add another provider:

1. Implement the `Provider` interface
2. Register it in `ProviderRegistry`
3. Add profiles to `config/models.yaml`
4. Run the shared adapter and route tests
5. Add a manual live evaluation before treating it as production-ready
