# Extension examples

These examples show the smallest supported seams for extending Core without
forking orchestration.

- `custom_provider.py` implements and registers a provider, then exercises it
  with the same normalised request and response contracts used by built-ins.
- `custom_stages.py` composes research and draft-review callbacks for a local
  host that needs alternative lifecycle execution.

Copy the relevant class or functions into the host application. Keep provider
credentials and vendor-specific payloads inside the adapter, and retain Core's
approval, validation, provenance, and publication boundaries.

Run the examples from a development checkout with:

```bash
uv run --frozen python examples/extensions/custom_provider.py
uv run --frozen python examples/extensions/custom_stages.py
```
