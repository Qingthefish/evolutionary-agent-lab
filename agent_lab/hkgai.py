"""Course-issued HKGAI endpoint with the existing strict chat/tool protocol.

Address/model authority: the instructor's API Information page, 2026-10-26.
Only the issued service is used; no Studio endpoint or provider fallback.
"""

from .deepseek import DeepSeekClient, DeepSeekHTTP


class HKGAIHTTP(DeepSeekHTTP):
    """Same bounded no-redirect/no-retry HTTP boundary, separate fixed host."""

    endpoint = "https://api1.hkgai.net/v1/chat/completions"


class HKGAIClient(DeepSeekClient):
    """Use standard chat fields; do not send DeepSeek-specific thinking options.

    Strict usage, tool-call IDs and finish checks remain unchanged. Unsupported
    or truncated responses release no tools; live compatibility needs evidence.
    """

    request_options = {}
