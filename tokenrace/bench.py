"""Logica di misura di TokenRace, indipendente da Streamlit.

Tutti i server vengono misurati con lo stesso codice:
POST /chat/completions in streaming, cronometrato lato client con time.perf_counter().
"""

import json
import threading
import time

import psutil
import requests


class ServerError(Exception):
    """Errore da mostrare all'utente.

    code   chiave del messaggio tradotto (sezione [err] di locales/*.toml)
    params segnaposto del messaggio, es. url o status
    """

    def __init__(self, code: str, **params):
        super().__init__(code)
        self.code = code
        self.params = params


def estimate_tokens(text: str) -> int:
    """Stima grossolana: circa 4 caratteri per token."""
    return max(1, round(len(text) / 4))


def build_prompts(texts: dict, target_chars: int) -> dict:
    """Crea i prompt "short", "long" e "cache" a partire dai testi di config/prompts.toml."""
    sections, n = [], 1
    while sum(len(s) for s in sections) < target_chars:
        sections.append(f"{texts['long_section']} {n}. {texts['long_paragraph']}")
        n += 1
    sections.insert(len(sections) // 2, texts["long_secret"])
    context = "\n".join(sections)
    long_prompt = f"{texts['long_intro']}\n\n{context}\n\n{texts['long_question']}"
    return {"short": texts["short"], "long": long_prompt, "cache": long_prompt}


def _short_detail(text: str) -> str | None:
    """Testo d'errore corto; None se è una pagina HTML (risponde un altro programma)."""
    text = text.strip()
    return None if text.startswith("<") else text[:300]


def _http_error(status: int, text: str) -> ServerError:
    detail = _short_detail(text)
    if detail is None:
        return ServerError("http_other_program", status=status)
    return ServerError("http", status=status, detail=detail)


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def fetch_models(base_url: str, api_key: str = "", timeout: float = 5) -> list[str]:
    """Legge l'elenco dei modelli con GET /models."""
    url = base_url.rstrip("/") + "/models"
    try:
        r = requests.get(url, timeout=timeout, headers=auth_headers(api_key))
    except requests.exceptions.ConnectionError:
        raise ServerError("connect", url=base_url)
    except requests.exceptions.Timeout:
        raise ServerError("timeout", url=base_url)
    if r.status_code in (401, 403):
        raise ServerError("auth", status=r.status_code)
    if r.status_code != 200:
        raise _http_error(r.status_code, r.text)
    try:
        data = r.json().get("data", [])
    except ValueError:
        raise ServerError("not_json")
    return sorted(m.get("id", "") for m in data if m.get("id"))


class RamSampler:
    """Campiona la RAM dell'intero sistema a intervalli regolari e tiene il picco."""

    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.before = self._used()
        self.peak = self.before
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    @staticmethod
    def _used() -> float:
        vm = psutil.virtual_memory()
        return (vm.total - vm.available) / 1024**3  # GB

    def _loop(self):
        while not self._stop.wait(self.interval):
            self.peak = max(self.peak, self._used())

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self.peak = max(self.peak, self._used())


def run_once(base_url: str, model: str, prompt: str, temperature: float, seed: int,
             max_tokens: int, on_update=None, no_reasoning: dict | None = None,
             api_key: str = "", ram_interval: float = 0.5,
             timeout: tuple[float, float] = (5, 600)) -> dict:
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
        payload.update(no_reasoning)  # campi specifici del server (config/servers.toml)

    ram = RamSampler(ram_interval).start()
    reasoning, content = [], []
    n_chunk_reasoning = n_chunk_content = 0
    usage = None
    t_first = t_last = None

    try:
        t_send = time.perf_counter()  # timer avviato subito prima dell'invio
        try:
            resp = requests.post(url, json=payload, stream=True, timeout=timeout,
                                 headers=auth_headers(api_key))
        except requests.exceptions.ConnectionError:
            raise ServerError("connect", url=base_url)
        except requests.exceptions.Timeout:
            raise ServerError("read_timeout")

        with resp:
            if resp.status_code != 200:
                raise _http_error(resp.status_code, resp.text)
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
                    raise ServerError("server", detail=msg)
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
                            "chunks": n_chunk_reasoning + n_chunk_content,
                            "elapsed": now - t_send,
                            "ram_peak": ram.peak,
                        })
        t_end = time.perf_counter()
    finally:
        ram.stop()

    if t_first is None:
        raise ServerError("no_tokens")

    # --- Conteggio token ---------------------------------------------------
    n_chunk = n_chunk_reasoning + n_chunk_content
    estimated = False        # token presi dai chunk invece che da usage
    split_estimated = False  # ripartizione ragionamento/risposta stimata
    if usage and usage.get("completion_tokens") is not None:
        tok_out = int(usage["completion_tokens"])
        tok_in = usage.get("prompt_tokens")
        if tok_in is None:
            tok_in, estimated = estimate_tokens(prompt), True
        details = usage.get("completion_tokens_details") or {}
        if details.get("reasoning_tokens") is not None:
            tok_reason = int(details["reasoning_tokens"])
        elif n_chunk_reasoning:
            tok_reason, split_estimated = round(tok_out * n_chunk_reasoning / n_chunk), True
        else:
            tok_reason = 0
    else:
        estimated = True
        tok_out, tok_in, tok_reason = n_chunk, estimate_tokens(prompt), n_chunk_reasoning
    tok_answer = max(0, tok_out - tok_reason)

    ttft = t_first - t_send
    gen_span = t_last - t_first
    return {
        "ttft": ttft,
        "tok_s_gen": (tok_out - 1) / gen_span if tok_out > 1 and gen_span > 0 else None,
        "tok_s_eff": tok_out / (t_last - t_send) if t_last > t_send else None,
        "total": t_end - t_send,
        "tok_in": int(tok_in),
        "tok_out": tok_out,
        "tok_reason": tok_reason,
        "tok_answer": tok_answer,
        "prompt_tok_s": tok_in / ttft if ttft > 0 else None,
        "ram_before": ram.before,
        "ram_peak": ram.peak,
        "estimated": estimated,
        "split_estimated": split_estimated,
        "reasoning": "".join(reasoning),
        "content": "".join(content),
    }
