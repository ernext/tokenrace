"""TokenRace - Local LLM Speed Test.

Interfaccia Streamlit. La logica di misura sta in tokenrace/bench.py,
i valori modificabili in config/, i testi tradotti in locales/.

Avvio: streamlit run app.py
Licenza: MIT
"""

import base64
import json
import os
import time
import uuid
from datetime import datetime

import altair as alt  # incluso con Streamlit
import pandas as pd
import streamlit as st

from tokenrace import bench
from tokenrace.config import ROOT, load_defaults, load_prompts, load_servers
from tokenrace.i18n import Translator, language_info

# Metriche riassunte nella tabella di riepilogo (chiavi interne del CSV)
SUMMARY_METRICS = ["ttft", "tok_s_gen", "tok_s_eff", "total", "prompt_tok_s"]
# Metriche sulla sola risposta visibile: nel riepilogo solo se c'è ragionamento
VISIBLE_METRICS = ["ttft_answer", "tok_s_visible"]
# Colonne della tabella delle ripetizioni del test in corso
RUN_COLUMNS = ["run", "cold"] + SUMMARY_METRICS + ["tok_out"]
# Spiegazione (sezione [help]) di ciascuna colonna; le altre usano [colhelp]
COLUMN_HELP = {"ttft": "help.ttft", "tok_s_gen": "help.gen", "tok_s_eff": "help.eff",
               "total": "help.total", "prompt_tok_s": "help.prompt_speed",
               "ram_before": "help.ram_before", "ram_peak": "help.ram_peak",
               "ttft_answer": "help.ttft_answer", "tok_s_visible": "help.visible"}
PRESET_IDS = ["short", "long", "cache"]


# ---------------------------------------------------------------------------
# Utilità
# ---------------------------------------------------------------------------

def fmt(v, dec=2):
    return "—" if v is None else f"{v:.{dec}f}"


def reasoning_md(t, text: str) -> str:
    if not text:
        return ""
    return f"> 💭 *{t('label.reasoning')}:* " + text[-3000:].replace("\n", " ") + "\n\n"


def status_badge(text: str, state: str) -> str:
    """Etichetta dello stato della ripetizione (state: running, done)."""
    return (f'<div class="tr-status-wrap"><span class="tr-status tr-status-{state}">'
            f'<span class="tr-dot"></span>{text}</span></div>')


def error_text(t, e: bench.ServerError) -> str:
    return t(f"err.{e.code}", **e.params)


def pick_language(languages: list[str], default: str) -> str:
    """Lingua indicata nell'URL (?lang=), altrimenti quella predefinita."""
    qp = st.query_params.get("lang")
    env = os.environ.get("TOKENRACE_LANG")  # impostata dal comando `tokenrace --lang`
    return qp if qp in languages else env if env in languages else default


def show_table(t, df: pd.DataFrame):
    """Mostra un DataFrame con colonne interne tradotte e spiegazioni nelle intestazioni."""
    names, config = {}, {}
    for c in df.columns:
        base, _, stat = c.partition("·")
        names[c] = t(f"col.{base}") + (f" · {t('stat.' + stat)}" if stat else "")
        help_key = COLUMN_HELP.get(base, f"colhelp.{base}")
        if base in ("server", "model"):
            config[names[c]] = st.column_config.TextColumn(width="medium")
        elif t.has(help_key):
            config[names[c]] = st.column_config.Column(help=t(help_key))
    st.dataframe(df.rename(columns=names), hide_index=True, width="stretch", column_config=config)


def has_reasoning(m) -> bool:
    """True se nel run c'è stato ragionamento separato dalla risposta visibile.

    Oltre ai token dichiarati si guarda se il TTFT della risposta differisce dal
    TTFT: un server può inviare reasoning_content dichiarando 0 token di ragionamento.
    """
    return m["tok_reason"] > 0 or m["ttft_answer"] != m["ttft"]


def make_row(ctx, rip: int, m: dict) -> dict:
    p = ctx["params"]
    return {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "server": ctx["server"].name,
        "url": ctx["base_url"],
        "model": ctx["model"],
        "prompt_type": ctx["preset"],
        "prompt_lang": ctx["lang"],
        "run": rip,
        "cold": rip == 1,
        "temperature": p["temperature"],
        "seed": p["seed"],
        "max_tokens": p["max_tokens"],
        "repetitions": p["repetitions"],
        "no_reasoning": bool(p["no_reasoning"]),
        "no_reasoning_fields": json.dumps(p["no_reasoning"]) if p["no_reasoning"] else "",
        **{k: m[k] for k in ("ttft", "tok_s_gen", "tok_s_eff", "total", "tok_in", "tok_out",
                             "tok_reason", "tok_answer", "prompt_tok_s", "ram_before",
                             "ram_peak", "estimated", "split_estimated",
                             "ttft_answer", "tok_s_visible")},
    }


# ---------------------------------------------------------------------------
# Sezioni della pagina
# ---------------------------------------------------------------------------

# Mascotte nell'intestazione, incorporata nella pagina come data URI
LOGO = "data:image/svg+xml;base64," + base64.b64encode(
    (ROOT / "assets" / "logo" / "tokenrace-icon.svg").read_bytes()).decode()


def render_header(t, n_servers: int, languages: list[str], lang: str) -> str:
    left, right = st.columns([6, 1], vertical_alignment="center")
    left.markdown(
        f"""<div class="tr-hero"><h1><img src="{LOGO}" alt="">Token<span>Race</span></h1>
        <p>{t('app.tagline')}</p>
        <span class="tr-pill">{t('app.servers_pill', n=n_servers)}</span></div>""",
        unsafe_allow_html=True)
    info = {code: language_info(code) for code in languages}
    # Il valore iniziale arriva da st.session_state["lang_choice"], impostato in main()
    choice = right.segmented_control(
        t("label.language"), languages, key="lang_choice",
        format_func=lambda c: f"{info[c]['flag']} {c.upper()}",
        label_visibility="collapsed", help=t("help.language"))
    return choice or lang


def render_server_form(t, servers, measure):
    ss = st.session_state
    by_id = {s.id: s for s in servers}
    with st.container(border=True):
        st.markdown(f"##### {t('section.server')}")
        c1, c2, c5, c3, c4 = st.columns([1.4, 1.9, 0.9, 2, 1.6], vertical_alignment="bottom")
        server = by_id[c1.selectbox(t("label.server"), list(by_id), key="server",
                                    format_func=lambda i: by_id[i].name, help=t("help.server"))]
        base_url = c2.text_input(t("label.url"), value=server.url, key=f"url_{server.id}",
                                 help=t("help.url"))
        api_key = c5.text_input(t("label.api_key"), type="password", key=f"key_{server.id}",
                                help=t("help.api_key"))
        error = None
        if c4.button(t("label.refresh"), help=t("help.refresh"), width="stretch"):
            try:
                ss.models[base_url] = bench.fetch_models(base_url, api_key,
                                                         measure["models_timeout_s"])
                if not ss.models[base_url]:
                    error = ("warning", t("msg.no_models"))
            except bench.ServerError as e:
                ss.models.pop(base_url, None)
                error = ("error", error_text(t, e))
        models = ss.models.get(base_url, [])
        model = c3.selectbox(t("label.model"), models, key=f"model_{base_url}",
                             placeholder=t("label.model_placeholder"),
                             index=0 if models else None, help=t("help.model"))
        note = t(f"server_notes.{server.id}")
        start = f"**{t('label.start_cmd')}:** `{server.start}` · " if server.start else ""
        st.caption(start + note)
        if error:
            getattr(st, error[0])(error[1])
    return server, base_url, api_key, model


def render_prompt_form(t, server, presets, defaults, model):
    ss = st.session_state
    d = defaults["params"]
    with st.container(border=True):
        st.markdown(f"##### {t('section.prompt')}")
        r = st.columns([1.3, 1, 1, 1, 1, 1.2, 1], vertical_alignment="bottom")
        # Una chiave per lingua: le etichette cambiano con la lingua, il valore scelto
        # (short/long/cache) è tenuto a parte in ss.preset.
        widget_key = f"preset_{t.lang}"

        def on_preset():
            ss.preset = ss[widget_key]
            ss.prompt = presets[ss.preset]

        r[0].selectbox(t("label.preset"), PRESET_IDS, index=PRESET_IDS.index(ss.preset),
                       key=widget_key, format_func=lambda i: t(f"preset.{i}"),
                       on_change=on_preset, help=t("help.preset"))
        params = {
            "temperature": r[1].number_input(t("label.temperature"), 0.0, 2.0, float(d["temperature"]),
                                             0.1, key="temperature", help=t("help.temperature")),
            "seed": int(r[2].number_input(t("label.seed"), value=int(d["seed"]), step=1, key="seed",
                                          help=t("help.seed"))),
            "max_tokens": int(r[3].number_input(t("label.max_tokens"), 1, 32768, int(d["max_tokens"]),
                                                64, key="max_tokens", help=t("help.max_tokens"))),
            "repetitions": int(r[4].number_input(t("label.repetitions"), 1, 50, int(d["repetitions"]),
                                                 1, key="repetitions", help=t("help.repetitions"))),
        }
        start = r[5].button(t("label.start"), type="primary", disabled=not model,
                            help=t("help.start"), width="stretch")
        stop = r[6].button(t("label.stop"), help=t("help.stop"), width="stretch")

        prompt = st.text_area(t("label.prompt"), key="prompt", height=90, help=t("help.prompt"))
        n1, n2 = st.columns([3, 1.2], vertical_alignment="center")
        n1.caption(f"**{t('preset.' + ss.preset)}**: {t('preset_descr.' + ss.preset)} · "
                   + t("preset_descr.token_estimate",
                       n=f"{bench.estimate_tokens(prompt):,}".replace(",", ".")))
        fields = json.dumps(server.no_reasoning)
        state = t("msg.nr_tested") if server.no_reasoning_tested else t("msg.nr_untested")
        nr_on = n2.toggle(t("label.no_reasoning"), key="no_reasoning",
                          help=t("help.no_reasoning") + "\n\n"
                          + t("msg.nr_help_suffix", server=server.name, fields=fields) + f" ({state}).")
        params["no_reasoning"] = server.no_reasoning if nr_on else None
        params["reasoning_fields"] = server.no_reasoning if nr_on else server.reasoning_on
        if nr_on:
            st.caption(t("msg.nr_sends", fields=fields, state=state))
        if stop:
            st.warning(t("msg.stopped"))
    return prompt, params, start


def run_test(t, ctx, prompt, run_id_label, measure, resp_box, status_box, live_box, reps_box):
    """Esegue le ripetizioni aggiornando risposta e misure in tempo reale."""
    ss = st.session_state
    p = ctx["params"]
    rows = []
    for rip in range(1, p["repetitions"] + 1):
        text = prompt
        if ctx["preset"] in ("short", "long"):
            text = f"[{run_id_label}: {uuid.uuid4()}]\n{prompt}"
        last_ui = [0.0]
        status = t("msg.run_status", i=rip, n=p["repetitions"]) + (t("msg.cold") if rip == 1 else "")
        status_box.markdown(status_badge(f"{status} · {t('msg.in_progress')}", "running"),
                            unsafe_allow_html=True)

        def on_update(r_txt, c_txt, live, status=status):
            now = time.perf_counter()
            if now - last_ui[0] < measure["ui_refresh_s"]:
                return
            last_ui[0] = now
            resp_box.markdown(reasoning_md(t, r_txt) + c_txt)
            with live_box.container():
                a, b = st.columns(2)
                a.metric(t("metric.ttft"), f"{live['ttft']:.2f}", help=t("help.ttft"), border=True)
                b.metric(t("metric.chunks"), live["chunks"], help=t("help.chunks"), border=True)
                a.metric(t("metric.elapsed"), f"{live['elapsed']:.1f}", help=t("help.elapsed"),
                         border=True)
                b.metric(t("metric.ram_peak"), f"{live['ram_peak']:.1f}", help=t("help.ram_peak"),
                         border=True)

        try:
            m = bench.run_once(ctx["base_url"], ctx["model"], text, p["temperature"], p["seed"],
                               p["max_tokens"], on_update, p["reasoning_fields"], ctx["api_key"],
                               ram_interval=measure["ram_interval_s"],
                               timeout=(measure["connect_timeout_s"], measure["read_timeout_s"]))
        except bench.ServerError as e:
            status_box.empty()
            st.error(error_text(t, e))
            break

        resp_box.markdown(reasoning_md(t, m["reasoning"]) + m["content"])
        status_box.markdown(status_badge(f"{status} · {t('msg.completed')}", "done"),
                            unsafe_allow_html=True)
        row = make_row(ctx, rip, m)
        ss.history.append(row)
        rows.append(row)

        with live_box.container():
            a, b, c = st.columns(3)
            a.metric(t("metric.ttft"), fmt(m["ttft"]), help=t("help.ttft"), border=True)
            b.metric(t("metric.gen"), fmt(m["tok_s_gen"], 1), help=t("help.gen"), border=True)
            c.metric(t("metric.eff"), fmt(m["tok_s_eff"], 1), help=t("help.eff"), border=True)
            a.metric(t("metric.total"), fmt(m["total"]), help=t("help.total"), border=True)
            b.metric(t("metric.tokens_io"), f"{m['tok_in']}/{m['tok_out']}", help=t("help.tokens_io"),
                     border=True)
            c.metric(t("metric.prompt_speed"), fmt(m["prompt_tok_s"], 0), help=t("help.prompt_speed"),
                     border=True)
            a.metric(t("metric.split"), f"{m['tok_reason']}/{m['tok_answer']}", help=t("help.split"),
                     border=True)
            b.metric(t("metric.ram_before"), f"{m['ram_before']:.1f}", help=t("help.ram_before"),
                     border=True)
            c.metric(t("metric.ram_peak"), f"{m['ram_peak']:.1f}", help=t("help.ram_peak"), border=True)
            if has_reasoning(m):
                # "≈": i token della risposta vengono da una ripartizione stimata
                approx = "≈" if m["split_estimated"] and m["tok_s_visible"] is not None else ""
                a.metric(t("metric.ttft_answer"), fmt(m["ttft_answer"]), help=t("help.ttft_answer"),
                         border=True)
                b.metric(t("metric.visible"), approx + fmt(m["tok_s_visible"], 1),
                         help=t("help.visible"), border=True)
            st.caption(t("msg.ram_note"))
            if m["estimated"]:
                st.warning(t("msg.estimated"))
            if p["no_reasoning"] and m["tok_reason"] > 0:
                st.warning(t("msg.reasoning_still"))
            if m["split_estimated"]:
                st.caption(t("msg.split_estimated"))

        with reps_box.container():
            show_table(t, pd.DataFrame(rows)[RUN_COLUMNS].round(2))


def render_results(t, primary_color: str):
    ss = st.session_state
    with st.container(border=True):
        st.markdown(f"##### {t('section.results')}")
        if not ss.history:
            st.info(t("msg.no_results"))
            return
        df = pd.DataFrame(ss.history)
        for c in VISIBLE_METRICS:  # tutte None diventano NaN: mediana/min/max senza errori
            df[c] = pd.to_numeric(df[c])
        df["prompt_type"] = df["prompt_type"].map(lambda i: t(f"preset.{i}"))
        keys = ["server", "model", "prompt_type"]
        warm = df[~df["cold"]]
        medians, mins, maxs = [], [], []
        reasoned = (df["tok_reason"] > 0) | (df["ttft_answer"] != df["ttft"])
        for m in SUMMARY_METRICS + (VISIBLE_METRICS if reasoned.any() else []):
            medians.append(warm.groupby(keys)[m].median().rename(f"{m}·median"))
            mins.append(df.groupby(keys)[m].min().rename(f"{m}·min"))
            maxs.append(df.groupby(keys)[m].max().rename(f"{m}·max"))
        summary = pd.concat(medians + mins + maxs, axis=1).reset_index()

        g1, g2 = st.columns([3, 2])
        with g1:
            st.markdown(t("label.summary"))
            show_table(t, summary.round(2))
        with g2:
            st.markdown(t("label.chart"))
            if warm.empty:
                st.caption(t("msg.need_two"))
            else:
                # Una barra per server e modello; il tipo di prompt si aggiunge
                # all'etichetta solo se nello storico ce n'è più di uno.
                groups = keys if warm["prompt_type"].nunique() > 1 else keys[:2]
                bars = warm.groupby(groups)["tok_s_eff"].median().rename("tok/s").reset_index()
                axis = t("label.chart_axis")
                bars[axis] = bars[groups].astype(str).agg(" · ".join, axis=1)
                base = alt.Chart(bars).encode(
                    x=alt.X("tok/s:Q", title="tok/s"),
                    y=alt.Y(f"{axis}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=0)),
                    tooltip=[axis, alt.Tooltip("tok/s:Q", format=".1f")])
                chart = base.mark_bar(color=primary_color, cornerRadiusEnd=4) + base.mark_text(
                    align="left", dx=4, fontWeight="bold").encode(text=alt.Text("tok/s:Q", format=".1f"))
                st.altair_chart(chart.properties(height=50 + 45 * len(bars)), width="stretch")

        with st.expander(t("label.all_runs")):
            show_table(t, df.round(3))

        d1, d2, _ = st.columns([1, 1, 5])
        csv = df.rename(columns=lambda c: t(f"col.{c}")).to_csv(index=False).encode("utf-8")
        d1.download_button(t("label.download"), csv,
                           file_name=f"tokenrace_{datetime.now():%Y%m%d_%H%M%S}.csv",
                           mime="text/csv", help=t("help.download"), width="stretch")
        if d2.button(t("label.clear"), help=t("help.clear"), width="stretch"):
            ss.history = []
            st.rerun()


# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="TokenRace", page_icon=str(ROOT / "assets" / "logo" / "tokenrace-favicon.png"),
                       layout="wide")
    defaults = load_defaults()
    ui, measure = defaults["ui"], defaults["measure"]
    servers = load_servers()
    css = (ROOT / "assets" / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>:root {{--tr-primary: {ui['primary_color']};}}\n{css}</style>",
                unsafe_allow_html=True)

    ss = st.session_state
    ss.setdefault("history", [])
    ss.setdefault("models", {})

    # Lingua: scelta nell'intestazione e ricordata nell'URL (?lang=it).
    # Se l'URL cambia da fuori (link, ricarica), ha la precedenza sulla scelta in memoria.
    url_lang = pick_language(ui["languages"], ui["default_language"])
    if url_lang != ss.get("applied_lang"):
        ss.lang_choice = url_lang
    lang = ss.get("lang_choice") or ss.get("applied_lang") or url_lang
    t = Translator(lang, ui["fallback_language"])
    render_header(t, len(servers), ui["languages"], lang)
    st.query_params["lang"] = lang
    ss.applied_lang = lang

    all_prompts = load_prompts()
    target = defaults["long_prompt"]["target_chars"]
    prompt_texts = all_prompts.get(lang, all_prompts[ui["fallback_language"]])
    presets = bench.build_prompts(prompt_texts, target)
    ss.setdefault("preset", "short")
    # Alla prima apertura, o se cambia la lingua e il prompt non è stato modificato,
    # mostra il prompt pronto nella lingua scelta.
    old_lang = ss.get("prompt_lang")
    if "prompt" not in ss:
        ss.prompt = presets[ss.preset]
    elif old_lang and old_lang != lang and old_lang in all_prompts:
        if ss.prompt == bench.build_prompts(all_prompts[old_lang], target)[ss.preset]:
            ss.prompt = presets[ss.preset]
    ss.prompt_lang = lang

    server, base_url, api_key, model = render_server_form(t, servers, measure)
    prompt, params, start = render_prompt_form(t, server, presets, defaults, model)

    left, right = st.columns([3, 2])
    with left.container(border=True):
        st.markdown(f"##### {t('section.response')}")
        resp_box = st.container(height=ui["response_height"], border=False).empty()
    with right.container(border=True):
        h1, h2 = st.columns([3, 2], vertical_alignment="center")
        h1.markdown(f"##### {t('section.live')}")
        status_box = h2.empty()
        live_box = st.empty()
        reps_box = st.empty()

    if start and model:
        ctx = {"server": server, "base_url": base_url, "api_key": api_key, "model": model,
               "preset": ss.preset, "lang": lang, "params": params}
        run_test(t, ctx, prompt, prompt_texts["run_id"], measure, resp_box, status_box, live_box,
                 reps_box)
    else:
        resp_box.caption(t("msg.response_placeholder"))
        live_box.caption(t("msg.live_placeholder"))

    render_results(t, ui["primary_color"])
    repo = ui["repo_url"]
    st.markdown(f'<div class="tr-footer">TokenRace · {t("app.footer")} · '
                f'<a href="{repo}" target="_blank">{repo.removeprefix("https://")}</a></div>',
                unsafe_allow_html=True)


if __name__ == "__main__":
    main()
