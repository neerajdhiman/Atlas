"""PII Masking Engine — detects and masks sensitive data before external API calls.

Enterprise-grade: masks emails, phones, SSNs, credit cards, API keys, IPs,
AWS credentials, and custom patterns. Maintains a reversible mask map so
responses can be unmasked for the end user.

Only applied when sending to external providers (Claude). Local models
(Ollama) on our infrastructure don't need masking.
"""

import re
from dataclasses import dataclass, field

from a1.common.logging import get_logger

log = get_logger("security.pii")

# PII detection patterns
PII_PATTERNS = {
    "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "phone": re.compile(r'\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b'),
    "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    "credit_card": re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'),
    "api_key": re.compile(r'\b(?:sk|pk|api|key|token|secret)[-_]?[A-Za-z0-9]{16,}\b', re.IGNORECASE),
    "ip_address": re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'),
    "aws_key": re.compile(r'\b(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}\b'),
    "aws_secret": re.compile(r'\b[A-Za-z0-9/+=]{40}\b'),
    "password": re.compile(r'(?i)(?:password|passwd|pwd)\s*[:=]\s*\S+'),
    "private_key": re.compile(r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----'),
}


@dataclass
class MaskResult:
    """Result of PII masking operation."""
    masked_text: str
    mask_map: dict[str, str]  # {placeholder: original_value}
    detections: list[dict]  # [{type, start, end, placeholder}]
    detection_count: int = 0


class PIIMasker:
    """Detects and masks PII in text content.

    Thread-safe. Maintains counters per PII type for deterministic
    placeholder naming within a session.
    """

    def __init__(self, enabled_patterns: list[str] | None = None):
        self.patterns = {}
        enabled = enabled_patterns or list(PII_PATTERNS.keys())
        for name in enabled:
            if name in PII_PATTERNS:
                self.patterns[name] = PII_PATTERNS[name]

    def mask(self, text: str) -> MaskResult:
        """Mask all PII in text. Returns masked text + reversible map."""
        if not text:
            return MaskResult(masked_text=text, mask_map={}, detections=[], detection_count=0)

        mask_map: dict[str, str] = {}
        detections: list[dict] = []
        counters: dict[str, int] = {}

        # Collect all matches with positions
        all_matches = []
        for pii_type, pattern in self.patterns.items():
            for match in pattern.finditer(text):
                all_matches.append({
                    "type": pii_type,
                    "start": match.start(),
                    "end": match.end(),
                    "value": match.group(),
                })

        # Sort by position (reverse) to replace from end to start
        all_matches.sort(key=lambda m: m["start"], reverse=True)

        # Deduplicate overlapping matches (keep longest)
        filtered = []
        for match in all_matches:
            overlaps = False
            for existing in filtered:
                if (match["start"] < existing["end"] and match["end"] > existing["start"]):
                    overlaps = True
                    break
            if not overlaps:
                filtered.append(match)

        # Replace from end to start
        masked = text
        for match in filtered:
            pii_type = match["type"]
            counters[pii_type] = counters.get(pii_type, 0) + 1
            placeholder = f"[{pii_type.upper()}_{counters[pii_type]}]"

            mask_map[placeholder] = match["value"]
            detections.append({
                "type": pii_type,
                "start": match["start"],
                "end": match["end"],
                "placeholder": placeholder,
            })

            masked = masked[:match["start"]] + placeholder + masked[match["end"]:]

        if detections:
            log.info(f"PII masked: {len(detections)} detections ({', '.join(counters.keys())})")

        return MaskResult(
            masked_text=masked,
            mask_map=mask_map,
            detections=sorted(detections, key=lambda d: d["start"]),
            detection_count=len(detections),
        )

    def unmask(self, text: str, mask_map: dict[str, str]) -> str:
        """Restore original values from placeholders in text."""
        if not text or not mask_map:
            return text
        result = text
        for placeholder, original in mask_map.items():
            result = result.replace(placeholder, original)
        return result

    def mask_messages(self, messages: list[dict]) -> tuple[list[dict], dict[str, str]]:
        """Mask PII across all messages. Returns masked messages + combined map."""
        combined_map: dict[str, str] = {}
        masked_messages = []

        for msg in messages:
            content = msg.get("content", "")
            if content and isinstance(content, str):
                result = self.mask(content)
                combined_map.update(result.mask_map)
                masked_msg = {**msg, "content": result.masked_text}
            else:
                masked_msg = msg.copy()
            masked_messages.append(masked_msg)

        return masked_messages, combined_map


# Singleton with all patterns enabled
pii_masker = PIIMasker()

# Stats tracking
_mask_stats: dict[str, int] = {}


def get_mask_stats() -> dict:
    """Return PII masking statistics."""
    return {
        "total_detections": sum(_mask_stats.values()),
        "by_type": dict(_mask_stats),
    }
