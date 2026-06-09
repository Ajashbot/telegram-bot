import re
import random
import logging
from typing import List

logger = logging.getLogger(__name__)


def generate_variants(original: str, count: int = 20) -> List[str]:
    """Generate multiple smart variants of an ad text without changing links, numbers, or prices."""

    # Extract protected parts (links, numbers, prices)
    protected = {}
    counter = [0]

    def protect(match):
        key = f"__PROTECTED_{counter[0]}__"
        protected[key] = match.group(0)
        counter[0] += 1
        return key

    # Protect URLs
    text = re.sub(r'https?://\S+', protect, original)
    # Protect @usernames
    text = re.sub(r'@\w+', protect, text)
    # Protect prices (e.g. 100$, $100, 50.5 USD)
    text = re.sub(r'\$[\d,.]+|\d+[\d,.]*\s*(?:USD|SAR|AED|KWD|EGP|ريال|دولار|جنيه|درهم)', protect, text)
    # Protect phone numbers
    text = re.sub(r'\+?\d[\d\s\-]{7,}', protect, text)
    # Protect standalone numbers (4+ digits)
    text = re.sub(r'\b\d{4,}\b', protect, text)

    variants = []
    seen = set()

    intro_phrases = [
        "🌟 ", "✨ ", "💡 ", "🔥 ", "⭐ ", "📢 ", "👋 ", "🎯 ",
        "💎 ", "🚀 ", "", "", "", "", ""
    ]

    outro_phrases = [
        "\n\n✅ لا تتردد في التواصل!",
        "\n\n📲 تواصل معنا الآن",
        "\n\n🤝 نحن هنا لخدمتك",
        "\n\n⚡ احجز الآن",
        "\n\n💬 راسلنا للمزيد",
        "\n\n🎁 عروض حصرية بانتظارك",
        "\n\n🔗 للتفاصيل راسلنا",
        "",  # no outro sometimes
        "",
        "",
    ]

    reorder_patterns = [
        lambda t: t,  # original order
        lambda t: _move_last_sentence_first(t),
        lambda t: _add_line_breaks(t),
        lambda t: _compact_spaces(t),
    ]

    emoji_sets = [
        ["✅", "📌", "💫"],
        ["🔹", "🔸", "⚡"],
        ["👌", "💯", "🌈"],
        ["🎉", "🌺", "💪"],
        ["🔔", "📣", "🎁"],
    ]

    attempt = 0
    while len(variants) < count and attempt < count * 5:
        attempt += 1
        try:
            intro = random.choice(intro_phrases)
            outro = random.choice(outro_phrases)
            reorder = random.choice(reorder_patterns)
            emojis = random.choice(emoji_sets)

            modified = reorder(text)
            modified = _replace_bullets(modified, emojis)

            variant = intro + modified + outro

            # Restore protected parts
            for key, value in protected.items():
                variant = variant.replace(key, value)

            variant = variant.strip()

            if variant not in seen and variant != original:
                seen.add(variant)
                variants.append(variant)
        except Exception as e:
            logger.error(f"Variant generation error: {e}")

    # Always include the original as first variant if needed
    if original not in seen:
        # Restore protected from original text processing
        restored_original = original
        variants.insert(0, restored_original)

    return variants[:count]


def _move_last_sentence_first(text: str) -> str:
    sentences = re.split(r'(\n|\.(?:\s|$))', text)
    parts = [s for s in sentences if s.strip()]
    if len(parts) > 2:
        parts = [parts[-1]] + parts[:-1]
    return "\n".join(parts)


def _add_line_breaks(text: str) -> str:
    lines = text.split("\n")
    result = []
    for line in lines:
        result.append(line)
        if line.strip() and not line.startswith("__PROTECTED"):
            result.append("")
    return "\n".join(result)


def _compact_spaces(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def _replace_bullets(text: str, emojis: List[str]) -> str:
    bullet_patterns = ['•', '◆', '▪', '–', '-', '✔', '✅', '🔹', '🔸']
    lines = text.split('\n')
    result = []
    emoji_idx = 0
    for line in lines:
        stripped = line.strip()
        replaced = False
        for bp in bullet_patterns:
            if stripped.startswith(bp):
                new_emoji = emojis[emoji_idx % len(emojis)]
                emoji_idx += 1
                result.append(line.replace(bp, new_emoji, 1))
                replaced = True
                break
        if not replaced:
            result.append(line)
    return '\n'.join(result)
