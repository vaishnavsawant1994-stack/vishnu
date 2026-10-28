"""Assemble the one canonical browser Home shell for Web and desktop hosts."""

from pathlib import Path
import re


HOME_STYLES = (
    '<link rel="stylesheet" href="/iphone/p2-home.css">',
    '<link rel="stylesheet" href="/iphone/vishnu-os-workspaces.css">',
)

HOME_SCRIPTS = (
    '<script src="/iphone/p2-home.js" defer></script>',
    '<script src="/iphone/vishnu-os-workspaces.js" defer></script>',
    '<script src="/iphone/neural-sphere.js" defer></script>',
    '<script src="/iphone/runtime-assistant.js" defer></script>',
    '<script src="/iphone/recovery-complete.js" defer></script>',
    '<script src="/iphone/first-run.js" defer></script>',
    '<script src="/iphone/first-run-actions.js" defer></script>',
    '<script src="/iphone/agent-workforce-entry.js" defer></script>',
    '<script src="/iphone/our-products-entry.js" defer></script>',
)


def load_home_page(web_dir: Path) -> str:
    """Read and compose Home markup and its shared, idempotent UI injections."""
    page = (Path(web_dir) / 'index.html').read_text(encoding='utf-8')
    if '</head>' not in page or '</body>' not in page:
        raise ValueError('PWA Home shell must contain closing head and body elements')

    # The shared shell currently references dozens of classic scripts. Leaving
    # them parser-blocking serializes every local asset request before Home can
    # initialize. `defer` downloads them in parallel while preserving their
    # document order and running them before DOMContentLoaded.
    def defer_classic_script(match: re.Match[str]) -> str:
        attributes = match.group(1)
        if re.search(r'\b(?:async|defer)\b', attributes, flags=re.IGNORECASE):
            return match.group(0)
        return f'<script{attributes} defer>'

    page = re.sub(
        r'<script\b([^>]*\bsrc\s*=\s*["\'][^"\']+["\'][^>]*)>',
        defer_classic_script,
        page,
        flags=re.IGNORECASE,
    )

    for asset in HOME_STYLES:
        if asset not in page:
            page = page.replace('</head>', f'  {asset}\n</head>', 1)
    for asset in HOME_SCRIPTS:
        if asset not in page:
            page = page.replace('</body>', f'  {asset}\n</body>', 1)
    return page
