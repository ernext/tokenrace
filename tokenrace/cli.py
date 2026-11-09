"""Comando `tokenrace`: avvia l'app Streamlit."""

import argparse
import os
import sys

from . import __version__
from .config import ROOT, load_defaults


def main() -> None:
    languages = load_defaults()["ui"]["languages"]
    parser = argparse.ArgumentParser(prog="tokenrace", description="LLM inference speed test.")
    parser.add_argument("--port", type=int, help="port to listen on (default: 8501)")
    parser.add_argument("--lang", choices=languages, help="interface language")
    parser.add_argument("--version", action="version", version=f"tokenrace {__version__}")
    args = parser.parse_args()

    if args.lang:
        os.environ["TOKENRACE_LANG"] = args.lang
    # Senza questa opzione, al primo avvio Streamlit si ferma a chiedere un'email
    argv = ["streamlit", "run", str(ROOT / "app.py"), "--server.showEmailPrompt=false"]
    if args.port:
        argv.append(f"--server.port={args.port}")

    from streamlit.web import cli as stcli
    sys.argv = argv
    sys.exit(stcli.main())
