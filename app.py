"""TokenRace - Local LLM Speed Test.

Confronta la velocità di server LLM locali compatibili con le API OpenAI
(Ollama, LM Studio, Rapid-MLX, oMLX, llama.cpp, vLLM e altri) usando lo stesso
identico codice di misura per tutti.

Avvio: streamlit run app.py
Licenza: MIT
"""

import json
import threading
import time
import uuid
from datetime import datetime

import altair as alt  # incluso con Streamlit
import pandas as pd
import psutil
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

# nome: (URL base predefinito, come avviarlo, nota)
SERVERS = {
    # --- Mac Apple Silicon (MLX) ---
    "Ollama": ("http://localhost:11434/v1", "ollama serve", "Mac, Linux, Windows."),
    "LM Studio": ("http://localhost:1234/v1", "lms server start  (poi lms load <modello>)",
                  "Mac, Linux, Windows."),
    "Rapid-MLX": ("http://localhost:7659/v1", "avvia l'app Rapid-MLX Desktop  (da CLI: rapid-mlx serve <modello> --port 8000)",
                  "Solo Mac. L'app Desktop usa la porta 7659 e richiede la API key; la CLI usa la 8000."),
    "oMLX": ("http://localhost:8000/v1", "avvia oMLX dall'app o dalla sua CLI",
             "Solo Mac. Porta 8000 da fonti esterne: verificala nelle impostazioni di oMLX."),
    "mlx_lm.server": ("http://localhost:8080/v1", "mlx_lm.server --model <modello> --port 8080",
                      "Solo Mac. Server di riferimento MLX, senza ottimizzazioni extra."),
    # --- Multipiattaforma ---
    "llama.cpp (llama-server)": ("http://localhost:8080/v1", "llama-server -m <file.gguf> --port 8080",
                                 "Mac, Linux, Windows. Il motore usato da Ollama e LM Studio."),
    "vLLM": ("http://localhost:8000/v1", "vllm serve <modello>",
             "Linux con GPU NVIDIA/AMD. Il più usato in produzione."),
    "SGLang": ("http://localhost:30000/v1", "python -m sglang.launch_server --model-path <modello>",
               "Linux con GPU NVIDIA/AMD."),
    "Lemonade": ("http://localhost:13305/api/v1", "lemonade-server serve",
                 "Windows/Linux, ottimizzato per AMD Ryzen AI. Le versioni vecchie usano la porta 8000."),
    "Docker Model Runner": ("http://localhost:12434/engines/v1", "docker desktop enable model-runner --tcp 12434",
                            "Mac, Linux, Windows. Serve l'accesso TCP dall'host attivo."),
    "Unsloth Studio": ("http://localhost:8888/v1", "unsloth run --model <modello>",
                       "Porta 8888 presa dagli esempi: quella vera la stampa «unsloth run» all'avvio. "
                       "Serve la API key sk-unsloth-… (Studio → Impostazioni → API)."),
    "LocalAI": ("http://localhost:8080/v1", "local-ai run <modello>", "Mac, Linux, Windows."),
    "Jan": ("http://localhost:1337/v1", "in Jan: Impostazioni → Local API Server → Avvia",
            "Mac, Linux, Windows. Richiede la API key impostata in Jan."),
    "KoboldCpp": ("http://localhost:5001/v1", "koboldcpp --model <file.gguf>", "Mac, Linux, Windows."),
    "text-generation-webui": ("http://localhost:5000/v1", "avvia con l'opzione --api",
                              "Mac, Linux, Windows. Su Mac la porta 5000 è occupata dal Ricevitore AirPlay: "
                              "usa --api-port 5005 e cambia l'URL."),
}

# Come chiedere a ciascun server di non ragionare: (campi da aggiungere, provato?)
_CTK = {"chat_template_kwargs": {"enable_thinking": False}}
NO_REASONING = {
    "Ollama": ({"reasoning_effort": "none"}, True),
    "LM Studio": ({"reasoning_effort": "none", **_CTK}, True),
    "text-generation-webui": ({"enable_thinking": False}, False),
}
NO_REASONING_DEFAULT = (_CTK, False)  # server basati su llama.cpp, MLX, vLLM, SGLang


def no_reasoning_for(server: str):
    return NO_REASONING.get(server, NO_REASONING_DEFAULT)


PROMPT_BREVE = (
    "Scrivi un racconto molto dettagliato, di almeno 800 parole, su una guardiana "
    "di un faro su un'isola remota che una notte riceve un messaggio misterioso. "
    "Descrivi luoghi, personaggi, dialoghi e un finale sorprendente."
)

_PARAGRAFO = (
    "La città di Valdorino sorge su una collina circondata da vigneti e boschi di "
    "castagni. Nel corso dei secoli i suoi abitanti hanno costruito mulini, ponti "
    "di pietra e piccole botteghe artigiane lungo il fiume. Ogni primavera si "
    "tiene una fiera in cui i mercanti scambiano tessuti, formaggi stagionati e "
    "attrezzi agricoli, mentre i musicisti suonano nelle piazze fino a tarda sera. "
)
_TARGET_CARATTERI = 32_000  # circa 8.000 token (stima: 4 caratteri per token)


def build_long_prompt() -> str:
    sezioni, n = [], 1
    while sum(len(s) for s in sezioni) < _TARGET_CARATTERI:
        sezioni.append(f"Sezione {n}. {_PARAGRAFO}")
        n += 1
    meta = len(sezioni) // 2
    sezioni.insert(meta, "Nota importante: il codice segreto dell'archivio è AZZURRO-47. ")
    contesto = "\n".join(sezioni)
    return (
        "Leggi il seguente documento.\n\n"
        f"{contesto}\n\n"
        "Domanda: qual è il codice segreto dell'archivio? Rispondi solo con il codice."
    )


PROMPT_LUNGO = build_long_prompt()
PRESETS = {"Breve": PROMPT_BREVE, "Lungo": PROMPT_LUNGO, "Cache": PROMPT_LUNGO}


def stima_token(testo: str) -> int:
    return max(1, round(len(testo) / 4))


# ---------------------------------------------------------------------------
# Logica di misura (indipendente da Streamlit)
# ---------------------------------------------------------------------------


class ServerError(Exception):
    """Errore leggibile da mostrare all'utente."""


def breve(testo: str) -> str:
    """Testo d'errore corto e leggibile (niente pagine HTML)."""
    testo = testo.strip()
    if testo.startswith("<"):
        return "sulla porta risponde un altro programma o l'URL non è corretto."
    return testo[:300]


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def fetch_models(base_url: str, api_key: str = "") -> list:
    url = base_url.rstrip("/") + "/models"
    try:
        r = requests.get(url, timeout=5, headers=auth_headers(api_key))
    except requests.exceptions.ConnectionError:
        raise ServerError(f"Impossibile connettersi a {base_url}. Il server è avviato?")
    except requests.exceptions.Timeout:
        raise ServerError(f"Il server {base_url} non risponde (timeout).")
    if r.status_code in (401, 403):
        raise ServerError(f"Accesso negato (HTTP {r.status_code}): serve una API key valida, "
                          "oppure sulla porta risponde un altro programma.")
    if r.status_code != 200:
        raise ServerError(f"Errore HTTP {r.status_code} da {url}: {breve(r.text)}")
    try:
        data = r.json().get("data", [])
    except ValueError:
        raise ServerError("Risposta non valida da /models: sulla porta risponde un altro programma "
                          "o l'URL non è corretto.")
    return sorted(m.get("id", "") for m in data if m.get("id"))


class RamSampler:
    """Campiona la RAM dell'intero sistema ogni 0,5 secondi e tiene il picco."""

    def __init__(self, intervallo: float = 0.5):
        self.intervallo = intervallo
        self.prima = self._usata()
        self.picco = self.prima
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    @staticmethod
    def _usata() -> float:
        vm = psutil.virtual_memory()
        return (vm.total - vm.available) / 1024**3  # GB

    def _loop(self):
        while not self._stop.wait(self.intervallo):
            self.picco = max(self.picco, self._usata())

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self.picco = max(self.picco, self._usata())


def run_once(base_url: str, model: str, prompt: str, temperature: float, seed: int,
             max_tokens: int, on_update=None, no_reasoning: dict | None = None,
             api_key: str = "") -> dict:
    """Esegue una richiesta in streaming e restituisce le misure.

    on_update(reasoning_text, content_text, live) viene chiamata a ogni chunk.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "seed": seed,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if no_reasoning:
        payload.update(no_reasoning)  # campi specifici del server (vedi NO_REASONING)

    ram = RamSampler().start()
    reasoning, content = [], []
    n_chunk_reasoning = n_chunk_content = 0
    usage = None
    t_first = t_last = None

    try:
        t_send = time.perf_counter()  # timer avviato subito prima dell'invio
        try:
            resp = requests.post(url, json=payload, stream=True, timeout=(5, 600),
                                 headers=auth_headers(api_key))
        except requests.exceptions.ConnectionError:
            raise ServerError(f"Impossibile connettersi a {base_url}. Il server è avviato?")
        except requests.exceptions.Timeout:
            raise ServerError("Timeout in attesa della risposta del server.")

        with resp:
            if resp.status_code != 200:
                raise ServerError(f"Errore HTTP {resp.status_code}: {breve(resp.text)}")
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                if "error" in chunk:
                    err = chunk["error"]
                    msg = err.get("message", err) if isinstance(err, dict) else err
                    raise ServerError(f"Errore dal server: {msg}")
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    r_txt = delta.get("reasoning_content") or delta.get("reasoning") or ""
                    c_txt = delta.get("content") or ""
                    if not (r_txt or c_txt):
                        continue
                    now = time.perf_counter()
                    if t_first is None:
                        t_first = now
                    t_last = now
                    if r_txt:
                        reasoning.append(r_txt)
                        n_chunk_reasoning += 1
                    if c_txt:
                        content.append(c_txt)
                        n_chunk_content += 1
                    if on_update:
                        on_update("".join(reasoning), "".join(content), {
                            "ttft": t_first - t_send,
                            "chunk": n_chunk_reasoning + n_chunk_content,
                            "elapsed": now - t_send,
                            "ram_picco": ram.picco,
                        })
        t_end = time.perf_counter()
    finally:
        ram.stop()

    if t_first is None:
        raise ServerError("Il server non ha restituito alcun token.")

    # --- Conteggio token ---------------------------------------------------
    n_chunk = n_chunk_reasoning + n_chunk_content
    stimato = False      # token presi dai chunk invece che da usage
    split_stimato = False  # ripartizione ragionamento/risposta stimata
    if usage and usage.get("completion_tokens") is not None:
        tok_out = int(usage["completion_tokens"])
        tok_in = usage.get("prompt_tokens")
        if tok_in is None:
            tok_in, stimato = stima_token(prompt), True
        details = usage.get("completion_tokens_details") or {}
        if details.get("reasoning_tokens") is not None:
            tok_reason = int(details["reasoning_tokens"])
        elif n_chunk_reasoning:
            tok_reason, split_stimato = round(tok_out * n_chunk_reasoning / n_chunk), True
        else:
            tok_reason = 0
    else:
        stimato = True
        tok_out, tok_in, tok_reason = n_chunk, stima_token(prompt), n_chunk_reasoning
    tok_answer = max(0, tok_out - tok_reason)

    ttft = t_first - t_send
    gen_span = t_last - t_first
    return {
        "ttft": ttft,
        "tok_s_gen": (tok_out - 1) / gen_span if tok_out > 1 and gen_span > 0 else None,
        "tok_s_eff": tok_out / (t_last - t_send) if t_last > t_send else None,
        "totale": t_end - t_send,
        "tok_in": int(tok_in),
        "tok_out": tok_out,
        "tok_reason": tok_reason,
        "tok_answer": tok_answer,
        "prompt_tok_s": tok_in / ttft if ttft > 0 else None,
        "ram_prima": ram.prima,
        "ram_picco": ram.picco,
        "stimato": stimato,
        "split_stimato": split_stimato,
        "reasoning": "".join(reasoning),
        "content": "".join(content),
    }


# ---------------------------------------------------------------------------
# Interfaccia
# ---------------------------------------------------------------------------

METRICHE = [
    "TTFT (s)",
    "Generazione (tok/s)",
    "Velocità effettiva (tok/s)",
    "Tempo totale (s)",
    "Elab. prompt stimata (tok/s)",
]


# Spiegazioni brevi mostrate nell'icona "?" accanto alle etichette
H = {
    "server": "Il programma che esegue il modello. Va avviato a mano prima del test: il comando è indicato sotto.",
    "url": "Indirizzo delle API compatibili OpenAI del server, di solito termina con /v1.",
    "modello": "Il modello da provare, letto dal server con GET /models.",
    "api_key": "Facoltativa. Serve solo se il server la richiede (es. Jan, Unsloth Studio, o vLLM avviato con --api-key).",
    "aggiorna": "Chiede al server l'elenco dei modelli disponibili.",
    "preset": "Breve: risposta lunga. Lungo: ≈8.000 token di contesto. Cache: prompt lungo identico a ogni ripetizione.",
    "prompt": "Il testo inviato al modello. Puoi modificarlo liberamente.",
    "temperature": "Casualità della risposta. 0 = la più ripetibile, consigliata per i test.",
    "seed": "Numero fisso per rendere le risposte riproducibili, se il server lo supporta.",
    "max_tokens": "Numero massimo di token che il modello può generare.",
    "ripetizioni": "Quante volte ripetere la prova. La prima è «a freddo» ed esclusa dalla mediana.",
    "avvia": "Avvia le ripetizioni sul server e modello scelti.",
    "ferma": "Interrompe il test. Le ripetizioni già completate restano salvate.",
    "ttft": "Time To First Token: secondi dall'invio della richiesta al primo token ricevuto.",
    "gen": "Velocità di generazione pura: (token output − 1) / (ultimo token − primo token).",
    "eff": "Velocità vista dall'utente, attesa iniziale inclusa: token output / (ultimo token − invio).",
    "totale": "Secondi dall'invio della richiesta alla fine dello streaming.",
    "chunk": "Pezzi di testo ricevuti finora; circa un token ciascuno.",
    "trascorso": "Secondi dall'invio della richiesta.",
    "token_io": "Token del prompt (input) e token generati (output), da usage.",
    "prompt_s": "Velocità di elaborazione del prompt, stima: token input / TTFT. Include anche latenza e caricamento del modello.",
    "split": "Ragionamento / risposta: token spesi a ragionare e token della risposta vera e propria.",
    "ram_prima": "RAM in uso nell'intero sistema subito prima della richiesta.",
    "ram_picco": "RAM massima in uso nell'intero sistema durante la richiesta (campionata ogni 0,5 s).",
    "scarica": "Scarica tutte le ripetizioni della sessione in un file CSV.",
    "svuota": "Cancella lo storico dei risultati di questa sessione.",
    "no_reasoning": "Chiede al server di non ragionare, con il parametro adatto a ciascun server. "
                    "Alcuni modelli ragionano comunque: in quel caso compare un avviso.",
}

# Spiegazioni per le colonne delle tabelle
COL_HELP = {
    "TTFT (s)": H["ttft"],
    "Generazione (tok/s)": H["gen"],
    "Velocità effettiva (tok/s)": H["eff"],
    "Tempo totale (s)": H["totale"],
    "Elab. prompt stimata (tok/s)": H["prompt_s"],
    "A freddo": "Prima ripetizione del test: esclusa dalla mediana.",
    "Token input": "Token del prompt.",
    "Token output": "Token generati (ragionamento + risposta).",
    "Token ragionamento": "Token spesi a ragionare.",
    "Token risposta": "Token della risposta vera e propria.",
    "RAM sistema prima (GB)": H["ram_prima"],
    "RAM sistema picco (GB)": H["ram_picco"],
    "Conteggio stimato": "Sì se il server non ha fornito usage e i token sono contati dai chunk.",
    "Ragionamento/risposta stimati": "Sì se la divisione ragionamento/risposta è stimata dai chunk.",
}


def col_config(columns) -> dict:
    """Associa a ogni colonna la sua spiegazione (anche per «· mediana/min/max»)."""
    cfg = {c: st.column_config.TextColumn(width="medium")
           for c in ("Server", "Modello") if c in columns}
    for c in columns:
        base = c.split(" · ")[0]
        if base in COL_HELP:
            cfg[c] = st.column_config.Column(help=COL_HELP[base])
    return cfg


def to_row(server, url, model, tipo, rip, params, m) -> dict:
    return {
        "Data e ora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Server": server,
        "URL": url,
        "Modello": model,
        "Tipo prompt": tipo,
        "Ripetizione": rip,
        "A freddo": rip == 1,
        "Temperature": params["temperature"],
        "Seed": params["seed"],
        "Max tokens": params["max_tokens"],
        "Ripetizioni": params["ripetizioni"],
        "Ragionamento disattivato": bool(params["no_reasoning"]),
        "Parametro senza ragionamento": json.dumps(params["no_reasoning"]) if params["no_reasoning"] else "",
        "TTFT (s)": m["ttft"],
        "Generazione (tok/s)": m["tok_s_gen"],
        "Velocità effettiva (tok/s)": m["tok_s_eff"],
        "Tempo totale (s)": m["totale"],
        "Token input": m["tok_in"],
        "Token output": m["tok_out"],
        "Token ragionamento": m["tok_reason"],
        "Token risposta": m["tok_answer"],
        "Elab. prompt stimata (tok/s)": m["prompt_tok_s"],
        "RAM sistema prima (GB)": m["ram_prima"],
        "RAM sistema picco (GB)": m["ram_picco"],
        "Conteggio stimato": m["stimato"],
        "Ragionamento/risposta stimati": m["split_stimato"],
    }


def fmt(v, dec=2):
    return "—" if v is None else f"{v:.{dec}f}"


def on_preset_change():
    st.session_state.prompt = PRESETS[st.session_state.preset]


COMPACT_CSS = """
<style>
.block-container {padding-top: 2rem; padding-bottom: 1rem; max-width: 1400px;}
h5 {margin: 0 0 0.6rem 0 !important; padding: 0 !important;}
[data-testid="stVerticalBlock"] {gap: 0.5rem;}
[data-testid="stWidgetLabel"] p {font-size: 0.8rem;}
.stTextInput input, .stNumberInput input, .stTextArea textarea,
[data-baseweb="select"] div {font-size: 0.85rem;}
[data-testid="stCaptionContainer"] {margin-top: -0.3rem;}
[data-testid="stMetricValue"] {font-size: 1.5rem;}
[data-testid="stMetricLabel"] p {font-size: 0.75rem;}
.tr-hero {display: flex; align-items: baseline; gap: 0.8rem; flex-wrap: wrap;
          margin-bottom: 0.6rem;}
.tr-hero h1 {font-size: 2rem; margin: 0; padding: 0;}
.tr-hero h1 span {color: #FF5A1F;}
.tr-hero p {margin: 0; opacity: 0.65; font-size: 0.95rem;}
.tr-pill {display: inline-block; padding: 0.1rem 0.6rem; border-radius: 999px;
          background: rgba(255, 90, 31, 0.12); color: #FF5A1F; font-size: 0.75rem;
          font-weight: 600;}
.tr-footer {text-align: center; opacity: 0.55; font-size: 0.8rem; margin-top: 1.5rem;}
</style>
"""

HERO = """
<div class="tr-hero">
  <h1>🏁 Token<span>Race</span></h1>
  <p>Benchmark dei server LLM locali · stesso codice di misura per tutti</p>
  <span class="tr-pill">{n} server</span>
</div>
"""

FOOTER = """
<div class="tr-footer">
  TokenRace · open source, licenza MIT ·
  <a href="https://github.com/ernext/tokenrace" target="_blank">github.com/ernext/tokenrace</a>
</div>
"""


def reasoning_md(testo: str) -> str:
    if not testo:
        return ""
    return "> 💭 *Ragionamento:* " + testo[-3000:].replace("\n", " ") + "\n\n"


def main():
    st.set_page_config(page_title="TokenRace", page_icon="🏁", layout="wide")
    st.markdown(COMPACT_CSS, unsafe_allow_html=True)
    st.markdown(HERO.format(n=len(SERVERS)), unsafe_allow_html=True)

    ss = st.session_state
    ss.setdefault("history", [])
    ss.setdefault("models", {})
    ss.setdefault("preset", "Breve")
    ss.setdefault("prompt", PROMPT_BREVE)

    # --- 1. Server e modello --------------------------------------------------
    with st.container(border=True):
        st.markdown("##### 🖥️ Server e modello")
        c1, c2, c5, c3, c4 = st.columns([1.4, 1.9, 0.9, 2, 1.6], vertical_alignment="bottom")
        server = c1.selectbox("Server", list(SERVERS), help=H["server"])
        url_default, comando, nota = SERVERS[server]
        base_url = c2.text_input("URL base", value=url_default, key=f"url_{server}", help=H["url"])
        api_key = c5.text_input("API key", type="password", key=f"key_{server}", help=H["api_key"])
        errore = None
        if c4.button("🔄 Aggiorna modelli", help=H["aggiorna"], width="stretch"):
            try:
                ss.models[base_url] = fetch_models(base_url, api_key)
                if not ss.models[base_url]:
                    errore = ("warning", "Il server è attivo ma non ha modelli disponibili.")
            except ServerError as e:
                ss.models.pop(base_url, None)
                errore = ("error", str(e))
        modelli = ss.models.get(base_url, [])
        model = c3.selectbox("Modello", modelli, placeholder="Premi «Aggiorna modelli»",
                             index=0 if modelli else None, help=H["modello"])
        st.caption(f"**Avvio:** `{comando}` · {nota}")
        if errore:
            getattr(st, errore[0])(errore[1])

    # --- 2. Prompt e parametri ------------------------------------------------
    with st.container(border=True):
        st.markdown("##### 📝 Prompt e parametri")
        r = st.columns([1.3, 1, 1, 1, 1, 1.2, 1], vertical_alignment="bottom")
        r[0].selectbox("Prompt pronto", list(PRESETS), key="preset", on_change=on_preset_change,
                       help=H["preset"])
        params = {
            "temperature": r[1].number_input("Temperature", 0.0, 2.0, 0.0, 0.1, help=H["temperature"]),
            "seed": int(r[2].number_input("Seed", value=42, step=1, help=H["seed"])),
            "max_tokens": int(r[3].number_input("Max tokens", 1, 32768, 512, 64, help=H["max_tokens"])),
            "ripetizioni": int(r[4].number_input("Ripetizioni", 1, 50, 3, 1, help=H["ripetizioni"])),
        }
        avvia = r[5].button("▶️ Avvia test", type="primary", disabled=not model,
                            help=H["avvia"], width="stretch")
        ferma = r[6].button("⏹️ Ferma", help=H["ferma"], width="stretch")

        tipo = ss.preset
        descr = {
            "Breve": "prompt corto, risposta lunga, ID univoco a ogni ripetizione",
            "Lungo": "≈8.000 token di contesto, risposta breve, ID univoco a ogni ripetizione",
            "Cache": "stesso prompt lungo, identico a ogni ripetizione (misura la cache)",
        }
        prompt = st.text_area("Testo del prompt", key="prompt", height=90, help=H["prompt"])
        n1, n2 = st.columns([3, 1.2], vertical_alignment="center")
        n1.caption(f"**{tipo}**: {descr[tipo]} · stima token del prompt ≈ "
                   + f"{stima_token(prompt):,}".replace(",", ".") + " (caratteri / 4)")
        nr_payload, nr_provato = no_reasoning_for(server)
        nr_testo = json.dumps(nr_payload)
        nr_on = n2.toggle("Senza ragionamento", key="no_reasoning", help=H["no_reasoning"] + f"\n\nPer {server} invia: `{nr_testo}`"
                          + (" (provato)." if nr_provato else " (non ancora provato su questo server)."))
        params["no_reasoning"] = nr_payload if nr_on else None
        if nr_on:
            st.caption(f"Senza ragionamento → invia `{nr_testo}` · "
                       + ("provato con questo server" if nr_provato else "non ancora provato con questo server"))
        if ferma:
            st.warning("Test interrotto. Le ripetizioni completate sono state salvate.")

    # --- 3. Risposta e misure -------------------------------------------------
    left, right = st.columns([3, 2])
    with left.container(border=True):
        st.markdown("##### 💬 Risposta in streaming")
        resp_box = st.container(height=430, border=False).empty()
    with right.container(border=True):
        st.markdown("##### ⏱️ Misure in tempo reale")
        live_box = st.empty()
        reps_box = st.empty()
    if not (avvia and model):
        resp_box.caption("La risposta del modello comparirà qui durante il test.")
        live_box.caption("Le misure di ogni ripetizione compariranno qui.")

    if avvia and model:
        run_rows = []
        for rip in range(1, params["ripetizioni"] + 1):
            testo = prompt
            if tipo in ("Breve", "Lungo"):
                testo = f"[ID esecuzione: {uuid.uuid4()}]\n{prompt}"
            last_ui = [0.0]
            stato = f"Ripetizione {rip}/{params['ripetizioni']}" + (" · a freddo" if rip == 1 else "")

            def on_update(r_txt, c_txt, live, stato=stato):
                now = time.perf_counter()
                if now - last_ui[0] < 0.1:
                    return
                last_ui[0] = now
                resp_box.markdown(reasoning_md(r_txt) + c_txt)
                with live_box.container():
                    st.caption(f"🔴 {stato} · in corso")
                    a, b = st.columns(2)
                    a.metric("TTFT (s)", f"{live['ttft']:.2f}", help=H["ttft"], border=True)
                    b.metric("Chunk ricevuti", live["chunk"], help=H["chunk"], border=True)
                    a.metric("Trascorso (s)", f"{live['elapsed']:.1f}", help=H["trascorso"], border=True)
                    b.metric("RAM picco (GB)", f"{live['ram_picco']:.1f}", help=H["ram_picco"], border=True)

            try:
                m = run_once(base_url, model, testo, params["temperature"], params["seed"],
                             params["max_tokens"], on_update, params["no_reasoning"], api_key)
            except ServerError as e:
                st.error(str(e))
                break

            resp_box.markdown(reasoning_md(m["reasoning"]) + m["content"])
            row = to_row(server, base_url, model, tipo, rip, params, m)
            ss.history.append(row)
            run_rows.append(row)

            with live_box.container():
                st.caption(f"✅ {stato} · completata")
                a, b, c = st.columns(3)
                a.metric("TTFT (s)", fmt(m['ttft']), help=H["ttft"], border=True)
                b.metric("Gen. (tok/s)", fmt(m['tok_s_gen'], 1), help=H["gen"], border=True)
                c.metric("Effettiva (tok/s)", fmt(m['tok_s_eff'], 1), help=H["eff"], border=True)
                a.metric("Totale (s)", fmt(m['totale']), help=H["totale"], border=True)
                b.metric("Token in/out", f"{m['tok_in']}/{m['tok_out']}", help=H["token_io"], border=True)
                c.metric("Prompt (tok/s)", fmt(m['prompt_tok_s'], 0), help=H["prompt_s"], border=True)
                a.metric("Ragion./risp.", f"{m['tok_reason']}/{m['tok_answer']}", help=H["split"], border=True)
                b.metric("RAM prima (GB)", f"{m['ram_prima']:.1f}", help=H["ram_prima"], border=True)
                c.metric("RAM picco (GB)", f"{m['ram_picco']:.1f}", help=H["ram_picco"], border=True)
                st.caption("RAM = memoria in uso dell'intero sistema, non del solo server.")
                if m["stimato"]:
                    st.warning("⚠️ Conteggio stimato: il server non ha fornito usage, token contati dai chunk.")
                if params["no_reasoning"] and m["tok_reason"] > 0:
                    st.warning("⚠️ Ragionamento ancora attivo: questo server o modello ha ignorato la richiesta.")
                if m["split_stimato"]:
                    st.caption("Divisione ragionamento/risposta stimata dai chunk (il server non la fornisce).")

            cols = ["Ripetizione", "A freddo"] + METRICHE + ["Token output"]
            reps_box.dataframe(pd.DataFrame(run_rows)[cols].round(2), hide_index=True,
                               width="stretch", column_config=col_config(cols))

    # --- Risultati -------------------------------------------------------------
    with st.container(border=True):
        st.markdown("##### 📊 Risultati della sessione")
        if not ss.history:
            st.info("Nessun risultato ancora. Scegli server e modello, poi premi «Avvia test».")
        else:
            df = pd.DataFrame(ss.history)
            chiavi = ["Server", "Modello", "Tipo prompt"]
            caldi = df[~df["A freddo"]]
            mediane, minimi, massimi = [], [], []
            for m in METRICHE:
                mediane.append(caldi.groupby(chiavi)[m].median().rename(f"{m} · mediana"))
                minimi.append(df.groupby(chiavi)[m].min().rename(f"{m} · min"))
                massimi.append(df.groupby(chiavi)[m].max().rename(f"{m} · max"))
            riepilogo = pd.concat(mediane + minimi + massimi, axis=1).reset_index()

            g1, g2 = st.columns([3, 2])
            with g1:
                st.markdown("**Riepilogo** · mediana senza la ripetizione a freddo; min e max su tutte")
                st.dataframe(riepilogo.round(2), hide_index=True, width="stretch",
                             column_config=col_config(riepilogo.columns))
            with g2:
                st.markdown("**Velocità effettiva mediana per server e modello** (tok/s)")
                if caldi.empty:
                    st.caption("Servono almeno 2 ripetizioni per calcolare la mediana.")
                else:
                    # Una barra per server e modello; il tipo di prompt si aggiunge
                    # all'etichetta solo se nello storico ce n'è più di uno.
                    gruppi = chiavi if caldi["Tipo prompt"].nunique() > 1 else chiavi[:2]
                    barre = (caldi.groupby(gruppi)["Velocità effettiva (tok/s)"].median()
                             .rename("tok/s").reset_index())
                    barre["Server e modello"] = barre[gruppi].astype(str).agg(" · ".join, axis=1)
                    base = alt.Chart(barre).encode(
                        x=alt.X("tok/s:Q", title="tok/s"),
                        y=alt.Y("Server e modello:N", sort="-x", title=None,
                                axis=alt.Axis(labelLimit=0)),
                        tooltip=["Server e modello", alt.Tooltip("tok/s:Q", format=".1f")])
                    barre_chart = base.mark_bar(color="#FF5A1F", cornerRadiusEnd=4)
                    valori = base.mark_text(align="left", dx=4, fontWeight="bold").encode(
                        text=alt.Text("tok/s:Q", format=".1f"))
                    st.altair_chart((barre_chart + valori).properties(height=50 + 45 * len(barre)),
                                    width="stretch")

            with st.expander("Tutte le ripetizioni"):
                st.dataframe(df.round(3), hide_index=True, width="stretch",
                             column_config=col_config(df.columns))

            d1, d2, _ = st.columns([1, 1, 5])
            nome = f"tokenrace_{datetime.now():%Y%m%d_%H%M%S}.csv"
            d1.download_button("⬇️ Scarica CSV", df.to_csv(index=False).encode("utf-8"),
                               file_name=nome, mime="text/csv", help=H["scarica"], width="stretch")
            if d2.button("🗑️ Svuota risultati", help=H["svuota"], width="stretch"):
                ss.history = []
                st.rerun()

    st.markdown(FOOTER, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
