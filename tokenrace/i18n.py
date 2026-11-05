"""Traduzioni dell'interfaccia: un file locales/<lingua>.toml per lingua."""

from .config import ROOT, load_toml

LOCALES_DIR = ROOT / "locales"


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


class Translator:
    """t("sezione.chiave", **segnaposto) → testo nella lingua scelta.

    Se una chiave manca nella lingua scelta usa quella di riserva,
    e se manca anche lì restituisce la chiave stessa (così si nota subito).
    """

    def __init__(self, lang: str, fallback: str = "en"):
        self.lang = lang
        self._texts = _flatten(load_toml(LOCALES_DIR / f"{lang}.toml"))
        self._fallback = (_flatten(load_toml(LOCALES_DIR / f"{fallback}.toml"))
                          if fallback != lang else {})

    def __call__(self, key: str, **kwargs) -> str:
        text = self._texts.get(key, self._fallback.get(key, key))
        return text.format(**kwargs) if kwargs else text

    def has(self, key: str) -> bool:
        return key in self._texts or key in self._fallback


def language_info(lang: str) -> dict:
    """Nome e bandiera di una lingua, letti dalla sezione [meta] del suo file."""
    return load_toml(LOCALES_DIR / f"{lang}.toml").get("meta", {"name": lang, "flag": ""})
