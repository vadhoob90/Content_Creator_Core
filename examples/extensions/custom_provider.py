"""Demonstrate a minimal provider implementation and registration."""

from content_creator.domain import ModelRequest, ModelResponse, ModelSelection
from content_creator.providers import Provider, ProviderRegistry


class EchoProvider(Provider):
    """Return a deterministic response for local integration development."""

    name = "echo"

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a deterministic response from a normalized request."""
        return ModelResponse(
            text=request.user,
            provider=self.name,
            model=request.selection.model,
        )


def main() -> None:
    """Register the example provider and execute one normalized request."""
    registry = ProviderRegistry()
    registry.register("echo", EchoProvider())
    request = ModelRequest(
        role="writer",
        system="Return the supplied text.",
        user="Provider extension is connected.",
        selection=ModelSelection(
            provider="echo",
            profile="fast",
            model="echo-v1",
        ),
    )
    print(registry.get("echo").generate(request).text)


if __name__ == "__main__":
    main()
