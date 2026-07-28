# ADR 0001: Provider-neutral model contract

Status: accepted.

Agents and orchestration issue a normalized request containing role, prompts,
schema, tools and capability profile. Provider adapters alone translate that
request into vendor APIs. Model names live in `config/models.yaml`, never in
workflow decisions. This permits OpenAI, Anthropic and additional adapters to
share routing and tests.
