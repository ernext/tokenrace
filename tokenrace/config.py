"""Lettura dei file di configurazione in config/ (formato TOML)."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
# Nel pacchetto installato i dati stanno in tokenrace/_data, nella repo nella cartella principale
ROOT = _PACKAGE_DIR / "_data" if (_PACKAGE_DIR / "_data").is_dir() else _PACKAGE_DIR.parent
CONFIG_DIR = ROOT / "config"


def load_toml(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


@dataclass(frozen=True)
class Server:
    id: str
    name: str
    url: str
    start: str = ""
    no_reasoning: dict = field(default_factory=dict)
    no_reasoning_tested: bool = False


def load_servers() -> list[Server]:
    data = load_toml(CONFIG_DIR / "servers.toml")
    default = data.get("no_reasoning_default", {})
    servers = []
    for s in data.get("server", []):
        servers.append(Server(
            id=s["id"],
            name=s["name"],
            url=s["url"],
            start=s.get("start", ""),
            no_reasoning=s.get("no_reasoning", default.get("fields", {})),
            no_reasoning_tested=s.get("no_reasoning_tested", default.get("tested", False)),
        ))
    return servers


def load_defaults() -> dict:
    return load_toml(CONFIG_DIR / "defaults.toml")


def load_prompts() -> dict:
    return load_toml(CONFIG_DIR / "prompts.toml")
