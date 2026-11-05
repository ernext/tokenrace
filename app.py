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
    "Rapid-MLX": ("http://localhost:8000/v1", "rapid-mlx serve <modello> --port 8000",
                  "Solo Mac. Porta 8000 presa dagli esempi della documentazione."),
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
    cfg = {}
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
.block-container {padding-top: 2.5rem; padding-bottom: 1rem;}
h1 {font-size: 1.8rem !important; padding-bottom: 0.2rem !important;}
h5 {margin: 0.8rem 0 0.3rem 0 !important; padding: 0 !important;}
[data-testid="stVerticalBlock"] {gap: 0.5rem;}
[data-testid="stWidgetLabel"] p {font-size: 0.8rem;}
.stTextInput input, .stNumberInput input, .stTextArea textarea,
[data-baseweb="select"] div {font-size: 0.85rem;}
[data-testid="stCaptionContainer"] {margin-top: -0.4rem;}
</style>
"""


def main():
    st.set_page_config(page_title="TokenRace", layout="wide")
    st.markdown(COMPACT_CSS, unsafe_allow_html=True)
    st.title("🏁 TokenRace — Local LLM Speed Test")

    ss = st.session_state
    ss.setdefault("history", [])
    ss.setdefault("models", {})
    ss.setdefault("preset", "Breve")
    ss.setdefault("prompt", PROMPT_BREVE)

    # --- 1. Server e modello (una riga) ---------------------------------------
    st.markdown("##### 1. Server e modello")
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
    st.markdown("##### 2. Prompt")
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
    nr_on = n2.toggle("Senza ragionamento", help=H["no_reasoning"] + f"\n\nPer {server} invia: `{nr_testo}`"
                      + (" (provato)." if nr_provato else " (non ancora provato su questo server)."))
    params["no_reasoning"] = nr_payload if nr_on else None
    if nr_on:
        st.caption(f"Senza ragionamento → invia `{nr_testo}` · "
                   + ("provato con questo server" if nr_provato else "non ancora provato con questo server"))
    if ferma:
        st.warning("Test interrotto. Le ripetizioni completate sono state salvate.")

    # --- 3. Risposta e misure -------------------------------------------------
    st.markdown("##### 3. Risposta e misure")
    left, right = st.columns([3, 2])
    left.markdown("**Risposta (streaming)**")
    resp_box = left.empty()
    right.markdown("**Misure in tempo reale**")
    live_box = right.empty()
    reps_box = right.empty()

    if avvia and model:
        run_rows = []
        for rip in range(1, params["ripetizioni"] + 1):
            testo = prompt
            if tipo in ("Breve", "Lungo"):
                testo = f"[ID esecuzione: {uuid.uuid4()}]\n{prompt}"
            last_ui = [0.0]

            def on_update(r_txt, c_txt, live, rip=rip):
                now = time.perf_counter()
                if now - last_ui[0] < 0.1:
                    return
                last_ui[0] = now
                md = ""
                if r_txt:
                    md += "> 💭 *Ragionamento:* " + r_txt[-3000:].replace("\n", " ") + "\n\n"
                md += c_txt
                resp_box.markdown(md)
                with live_box.container():
                    st.caption(f"Ripetizione {rip}/{params['ripetizioni']}"
                               + (" — a freddo" if rip == 1 else ""))
                    a, b = st.columns(2)
                    a.metric("TTFT (s)", f"{live['ttft']:.2f}", help=H["ttft"])
                    b.metric("Chunk ricevuti", live["chunk"], help=H["chunk"])
                    a.metric("Trascorso (s)", f"{live['elapsed']:.1f}", help=H["trascorso"])
                    b.metric("RAM picco (GB)", f"{live['ram_picco']:.1f}", help=H["ram_picco"])

            try:
                m = run_once(base_url, model, testo, params["temperature"], params["seed"],
                             params["max_tokens"], on_update, params["no_reasoning"], api_key)
            except ServerError as e:
                st.error(str(e))
                break

            md = ""
            if m["reasoning"]:
                md += "> 💭 *Ragionamento:* " + m["reasoning"][-3000:].replace("\n", " ") + "\n\n"
            resp_box.markdown(md + m["content"])
            row = to_row(server, base_url, model, tipo, rip, params, m)
            ss.history.append(row)
            run_rows.append(row)

            with live_box.container():
                st.caption(f"Ripetizione {rip}/{params['ripetizioni']} completata"
                           + (" — a freddo" if rip == 1 else ""))
                a, b, c = st.columns(3)
                a.metric("TTFT (s)", fmt(m['ttft']), help=H["ttft"])
                b.metric("Gen. (tok/s)", fmt(m['tok_s_gen'], 1), help=H["gen"])
                c.metric("Effettiva (tok/s)", fmt(m['tok_s_eff'], 1), help=H["eff"])
                a.metric("Totale (s)", fmt(m['totale']), help=H["totale"])
                b.metric("Token in/out", f"{m['tok_in']}/{m['tok_out']}", help=H["token_io"])
                c.metric("Prompt (tok/s)", fmt(m['prompt_tok_s'], 0), help=H["prompt_s"])
                a.metric("Ragion./risp.", f"{m['tok_reason']}/{m['tok_answer']}", help=H["split"])
                b.metric("RAM prima (GB)", f"{m['ram_prima']:.1f}", help=H["ram_prima"])
                c.metric("RAM picco (GB)", f"{m['ram_picco']:.1f}", help=H["ram_picco"])
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
    st.markdown("##### Risultati della sessione")
    if not ss.history:
        st.info("Nessun risultato ancora. Avvia un test.")
        return

    df = pd.DataFrame(ss.history)
    chiavi = ["Server", "Modello", "Tipo prompt"]
    caldi = df[~df["A freddo"]]
    parti = []
    for m in METRICHE:
        med = caldi.groupby(chiavi)[m].median().rename(f"{m} · mediana")
        mn = df.groupby(chiavi)[m].min().rename(f"{m} · min")
        mx = df.groupby(chiavi)[m].max().rename(f"{m} · max")
        parti += [med, mn, mx]
    riepilogo = pd.concat(parti, axis=1).reset_index()
    st.markdown("**Riepilogo** (mediana senza la ripetizione a freddo; min e max su tutte)")
    st.dataframe(riepilogo.round(2), hide_index=True, width="stretch",
                 column_config=col_config(riepilogo.columns))

    st.markdown("**Velocità effettiva mediana per server (tok/s)**")
    if caldi.empty:
        st.caption("Servono almeno 2 ripetizioni per calcolare la mediana.")
    else:
        st.bar_chart(caldi.groupby("Server")["Velocità effettiva (tok/s)"].median())

    with st.expander("Tutte le ripetizioni"):
        st.dataframe(df.round(3), hide_index=True, width="stretch",
                     column_config=col_config(df.columns))

    d1, d2, _ = st.columns([1, 1, 6])
    nome = f"tokenrace_{datetime.now():%Y%m%d_%H%M%S}.csv"
    d1.download_button("⬇️ Scarica CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=nome, mime="text/csv", help=H["scarica"])
    if d2.button("🗑️ Svuota risultati", help=H["svuota"]):
        ss.history = []
        st.rerun()


if __name__ == "__main__":
    main()
