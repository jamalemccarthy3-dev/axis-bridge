# src/denoising_sanitization.py
import re

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_TAGS = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"\s+")


class DenoisingSanitizationEngine:
    def __init__(self, config):
        self.sensitivity = config.sensitivity
        self.noise_threshold = config.noise_threshold
        self.strip_html = getattr(config, "strip_html", True)
        self.max_length = getattr(config, "max_length", 8192)

    def filter_noise(self, raw_input):
        # processes input to strip away interference
        cleaned_input = raw_input.replace("noise_artifact", "").strip()
        return {"status": "denoised", "data": cleaned_input}

    def clean(self, raw_input):
        """Sanitise an incoming text stream: remove interference markers, HTML tags (if configured) and control characters,
        collapse whitespace, and enforce the buffer limit. -> {status, data, truncated, removed_chars}"""
        text = str(raw_input)
        out = self.filter_noise(text)["data"]
        if self.strip_html:
            out = _TAGS.sub("", out)
        out = _CONTROL.sub("", out)
        out = _SPACE.sub(" ", out).strip()
        truncated = len(out) > self.max_length
        if truncated:
            out = out[:self.max_length]
        return {"status": "sanitized", "data": out, "truncated": truncated, "removed_chars": len(text) - len(out)}

    def verify_clarity(self, stream):
        # confirms the signal is clear of interference: the share of interference markers must stay under the noise threshold
        text = str(stream)
        noise = text.count("noise_artifact") * len("noise_artifact")
        ratio = (noise / len(text)) if text else 0.0
        return {"status": "clear" if ratio <= self.noise_threshold else "noisy", "compliant": ratio <= self.noise_threshold, "noise_ratio": round(ratio, 4)}


denoising_sanitization = DenoisingSanitizationEngine      # the old lower-case name still works
