"""Update supported Markdown references into a closed draft package."""

import posixpath
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from ..storage import StorageError

_INLINE = re.compile(
    r"""(?<!\\)(!?)\[((?:\\.|[^\]\\\n])*)\]\("""
    r"""[ \t]*(?:<([^>\n]*)>|((?:\\.|[^()\s]|\([^()\n]*\))*))"""
    r"""(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'))?[ \t]*\)"""
)
_DEFINITION = re.compile(
    r"""^[ ]{0,3}\[([^\]\n]+)\]:[ \t]*(?:<([^>\n]+)>|(\S+))"""
    r"""(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'))?[ \t]*$""",
    re.MULTILINE,
)
_REFERENCE = re.compile(r"(?<!\\)(!?)\[([^\]\n]*)\]\[([^\]\n]*)\]")
_SHORTCUT_IMAGE = re.compile(r"(?<!\\)!\[([^\]\n]+)\](?![\[(])")


def rewrite_markdown(
    content: str, source_path: str, destinations: dict[str, str], alt_texts: dict[str, str]
) -> str:
    """Update local inline/reference links while preserving prose and code examples.

    Only governed local files may become package dependencies. Unsupported
    references fail before output, and code examples retain their original bytes.

    Args:
        content (str): Source Markdown text.
        source_path (str): Workspace-relative location of the source Markdown.
        destinations (dict[str, str]): Source-to-export path mapping for every packaged file.
        alt_texts (dict[str, str]): Approved or pending selected visual accessibility text.

    Returns:
        str: Markdown whose supported local links resolve within the package.

    Raises:
        StorageError: If local targets or Markdown link syntax cannot be safely resolved.
    """
    visible = _mask_code(content)
    if re.search(
        r"<(?:img|a|source|video|audio|iframe|object|embed|link|script|image|use)\b", visible, re.I
    ):
        raise StorageError(
            "Use Markdown links/images for draft export; HTML references are unsupported"
        )
    changes: dict[tuple[int, int], str] = {}
    definitions = _definitions(visible, source_path, destinations, changes)
    inline = list(_INLINE.finditer(visible))
    for match in inline:
        group = 3 if match.group(3) is not None else 4
        url = match.group(group)
        rewritten, target = _destination(url, source_path, destinations)
        changes[match.span(group)] = rewritten
        if match.group(1) and not url.strip():
            raise StorageError("Markdown image has an empty destination")
        if match.group(1) and target:
            changes[match.span(2)] = _alt(target, alt_texts)
    remaining = _mask_spans(
        visible, [m.span() for m in inline] + [m.span() for m in _DEFINITION.finditer(visible)]
    )
    if re.search(r"^[ ]{0,3}\[[^\]\n]+\]:", remaining, re.MULTILINE):
        raise StorageError("Use one-line Markdown reference definitions for draft export")
    _image_references(remaining, definitions, alt_texts, changes)
    if re.search(r"(?<!\\)\]\(", remaining):
        raise StorageError(
            "Markdown contains unsupported link syntax; use simple inline or reference links"
        )
    result = content
    for (start, end), replacement in sorted(changes.items(), reverse=True):
        result = result[:start] + replacement + result[end:]
    return result


def _image_references(
    remaining: str,
    definitions: dict[str, str | None],
    alt_texts: dict[str, str],
    changes: dict[tuple[int, int], str],
) -> None:
    """Update accessibility labels while preserving image reference identities.

    Args:
        remaining (str): Markdown with inline links and definitions masked.
        definitions (dict[str, str | None]): Resolved reference targets.
        alt_texts (dict[str, str]): Selected visual accessibility descriptions.
        changes (dict[tuple[int, int], str]): Collected exact-span replacements.

    Returns:
        None: Reference image changes are appended.

    Raises:
        StorageError: If an image or explicit link reference cannot be resolved.
    """
    references = list(_REFERENCE.finditer(remaining))
    for match in references:
        label = _label(match.group(3) or match.group(2))
        if label not in definitions:
            raise StorageError("Markdown contains an unresolved reference-style link")
        target = definitions[label]
        if match.group(1) and target:
            changes[match.span(2)] = _alt(target, alt_texts)
            if not match.group(3):
                changes[match.span(3)] = match.group(2)
    remaining = _mask_spans(remaining, [m.span() for m in references])
    for match in _SHORTCUT_IMAGE.finditer(remaining):
        label = _label(match.group(1))
        if label not in definitions:
            raise StorageError("Markdown contains an unresolved image reference")
        target = definitions[label]
        if target:
            changes[match.span()] = f"![{_alt(target, alt_texts)}][{match.group(1)}]"


def _definitions(
    visible: str, source: str, destinations: dict[str, str], changes: dict[tuple[int, int], str]
) -> dict[str, str | None]:
    """Resolve reference definitions and reject ambiguous duplicate labels.

    Args:
        visible (str): Markdown with code masked.
        source (str): Source artifact path.
        destinations (dict[str, str]): Package source mapping.
        changes (dict[tuple[int, int], str]): Collected exact-span replacements.

    Returns:
        dict[str, str | None]: Normalized reference labels and local source targets.

    Raises:
        StorageError: If a reference label is repeated.
    """
    definitions = {}
    for match in _DEFINITION.finditer(visible):
        label = _label(match.group(1))
        if label in definitions:
            raise StorageError("Markdown contains duplicate reference definitions")
        group = 2 if match.group(2) is not None else 3
        rewritten, target = _destination(match.group(group), source, destinations)
        definitions[label] = target
        changes[match.span(group)] = rewritten
    return definitions


def _destination(url: str, source: str, destinations: dict[str, str]) -> tuple[str, str | None]:
    """Resolve a local target only when it belongs to the exported package.

    Args:
        url (str): Markdown link destination.
        source (str): Source artifact path.
        destinations (dict[str, str]): Complete source-to-export mapping.

    Returns:
        tuple[str, str | None]: Rewritten URL and local source identity, if any.

    Raises:
        StorageError: If a local reference is unsupported or absent from the package.
    """
    parts = urlsplit(url)
    if parts.scheme in {"https", "http", "mailto"}:
        return url, None
    if parts.scheme or parts.netloc or parts.path.startswith("/") or "\\" in url:
        raise StorageError("Local Markdown links must use relative workspace paths")
    if not parts.path:
        return url, None
    decoded = unquote(parts.path)
    if decoded.startswith("/") or "\\" in decoded:
        raise StorageError("Encoded Markdown path leaves its source scope")
    target = posixpath.normpath(posixpath.join(posixpath.dirname(source), decoded))
    if target not in destinations:
        raise StorageError("Local Markdown link is not part of the draft package: " + target)
    rewritten = urlunsplit(
        ("", "", quote(destinations[target], safe="/-._~"), parts.query, parts.fragment)
    )
    return rewritten, target


def _alt(target: str, alt_texts: dict[str, str]) -> str:
    """Render selected visual alt text without breaking Markdown label syntax.

    Args:
        target (str): Selected source visual path.
        alt_texts (dict[str, str]): Visual accessibility descriptions.

    Returns:
        str: Markdown-escaped accessibility text.

    Raises:
        StorageError: If an image targets something other than selected governed media.
    """
    if target not in alt_texts:
        raise StorageError("Markdown images must reference selected governed visual assets")
    return re.sub(r"([\\\[\]])", r"\\\1", " ".join(alt_texts[target].splitlines()))


def _label(value: str) -> str:
    """Normalize reference labels using whitespace-insensitive case folding.

    Args:
        value (str): Reference label.

    Returns:
        str: Normalized reference identity.
    """
    return " ".join(value.split()).casefold()


def _mask_spans(content: str, spans: list[tuple[int, int]]) -> str:
    """Hide parsed structures while retaining offsets into the original Markdown.

    Args:
        content (str): Text whose offsets must remain stable.
        spans (list[tuple[int, int]]): Ranges to hide from subsequent parsing.

    Returns:
        str: Same-length string with selected spans replaced by spaces.
    """
    result = list(content)
    for start, end in spans:
        result[start:end] = " " * (end - start)
    return "".join(result)


def _mask_code(content: str) -> str:
    """Hide fenced, indented, and inline code from link rewriting.

    Args:
        content (str): Original Markdown.

    Returns:
        str: Same-length text retaining only non-code link candidates.
    """
    spans = []
    offset = 0
    fence = None
    for line in content.splitlines(keepends=True):
        marker = re.match(r"^[ ]{0,3}(`{3,}|~{3,})", line)
        if fence:
            spans.append((offset, offset + len(line)))
            if (
                marker
                and marker.group(1)[0] == fence[0]
                and len(marker.group(1)) >= len(fence)
                and not line[marker.end() :].strip()
            ):
                fence = None
        elif marker:
            fence = marker.group(1)
            spans.append((offset, offset + len(line)))
        elif line.startswith(("    ", "\t")):
            spans.append((offset, offset + len(line)))
        offset += len(line)
    visible = _mask_spans(content, spans)
    spans = [m.span() for m in re.finditer(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", visible, re.DOTALL)]
    return _mask_spans(visible, spans)
