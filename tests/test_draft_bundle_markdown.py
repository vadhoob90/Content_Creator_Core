import pytest

from content_creator.draft_bundles.markdown import rewrite_markdown
from content_creator.storage import StorageError

SOURCES = {
    "runs/article/final.md": "article.md",
    "runs/hook/final.md": "hook.md",
    "runs/article/visuals/my asset.svg": "assets/article-01-hero-r1.svg",
}
ALT = {"runs/article/visuals/my asset.svg": "A [clear] chart"}


def rewrite(text):
    return rewrite_markdown(text, "runs/article/final.md", SOURCES, ALT)


def test_inline_links_images_and_cross_member_anchors():
    text = (
        '![Old](<visuals/my asset.svg> "Caption")\n'
        "[Hook](../hook/final.md?view=draft#opening)\n"
        "[Site](https://example.com/a_(b)) [Email](mailto:a@example.com) [Self](#intro)"
    )
    result = rewrite(text)
    assert '![A \\[clear\\] chart](<assets/article-01-hero-r1.svg> "Caption")' in result
    assert "[Hook](hook.md?view=draft#opening)" in result
    assert result.splitlines()[2] == text.splitlines()[2]


@pytest.mark.parametrize("image", ["![Old][pic]", "![pic][]", "![pic]"])
def test_reference_images_preserve_labels_when_alt_text_changes(image):
    result = rewrite(image + '\n\n[pic]: <visuals/my asset.svg> "Title"\n')
    assert result.startswith("![A \\[clear\\] chart][pic]")
    assert '[pic]: <assets/article-01-hero-r1.svg> "Title"' in result


def test_code_examples_and_plain_text_remain_exact():
    text = (
        "`![sample](missing.svg)`\n```md\n![sample](missing.svg)\n```\n"
        "    [local](missing.md)\nPlain [text].\n~~~\n[example](no.md)\n~~~\n"
    )
    assert rewrite(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "![image](missing.svg)",
        "![empty]()",
        "[x]:\n  missing.md\n\n[x]",
        '<audio src="missing.mp3">',
        "[local](../unknown/final.md)",
        "[file](/etc/passwd)",
        "[file](%2Fetc/passwd)",
        "[file](file:///etc/passwd)",
        "[file](//example.com/file)",
        "[file](..%5Csecret)",
        "![not an image](../hook/final.md)",
        "![missing][ref]",
        "![missing]",
        "[x]: final.md\n[x]: final.md",
        '<img src="visuals/my asset.svg">',
        "[complex](one(two(three)).md)",
    ],
)
def test_export_rejects_unresolved_or_unsupported_references(text):
    with pytest.raises(StorageError):
        rewrite(text)


def test_adversarial_escape_sequence_does_not_backtrack_exponentially():
    import subprocess
    import sys

    code = r"""
from content_creator.draft_bundles.markdown import rewrite_markdown
from content_creator.storage import StorageError
try:
    rewrite_markdown("[](" + "\\!" * 4000, "runs/example/final.md", {}, {})
except StorageError:
    pass
else:
    raise AssertionError("Malformed link should be rejected")
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=5)
