# 🏁 TokenRace — Local LLM Speed Test

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-app-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Servers](https://img.shields.io/badge/servers-15-FF5A1F)](#supported-servers)
[![Languages](https://img.shields.io/badge/UI-English%20%7C%20Italiano-lightgrey)](#languages)

**English** · [Italiano](README.it.md)

Benchmark local LLM servers (Ollama, LM Studio, Rapid-MLX, oMLX, llama.cpp, vLLM and more) with **the exact same measuring code** for all of them.

A small [Streamlit](https://streamlit.io) app: pick a server and a model, start the test and watch TTFT, tokens per second, total time and RAM live, with a summary, a chart and CSV export.

<p align="center">
  <img src="docs/screenshot.png" alt="TokenRace: the same LFM3 1.7B model on Rapid-MLX and Ollama, with streaming response, live metrics and summary" width="900">
</p>
<p align="center"><sub>LFM3 1.7B on Rapid-MLX Desktop (8-bit) and Ollama (4-bit, nvfp4), "Short" prompt, no reasoning, 3 runs. Different quantizations: an example, not a ranking.</sub></p>

## Features

- Same method for every server: streaming `POST /chat/completions`, timed on the client with `time.perf_counter()`, never with the servers' own stats.
- Three preset tests: **Short** (long answer), **Long** (≈8,000 tokens of context) and **Cache** (identical prompt on every run).
- Streaming response and live metrics.
- Reasoning models timed correctly, with reasoning and answer tokens shown separately, plus a **No reasoning** switch.
- First run marked "cold" and excluded from the median.
- Summary with median, min and max, a chart per server and model, CSV export.
- English and Italian interface; servers, defaults and texts in easy-to-edit TOML files.
- Fully local: no database, accounts or telemetry.

## Requirements

- Python 3.11 or newer
- At least one local OpenAI-compatible LLM server, already running

Built for Apple Silicon Macs, works on Linux and Windows too.

## Install

```bash
git clone https://github.com/ernext/tokenrace.git
cd tokenrace
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

Then open http://localhost:8501. The interface opens in English; switch language with the selector at the top right, or open http://localhost:8501/?lang=it.

## Supported servers

TokenRace never installs or starts servers: start them yourself. They all speak the same OpenAI-compatible API, and the app shows the start command of the selected server.

If your server is not listed but is OpenAI-compatible, pick any entry and change the base URL, or add it to `config/servers.toml` (see below).

| Server | Default URL | Start | Notes |
|---|---|---|---|
| <img src="https://github.com/ollama.png?size=40" width="20" alt="">&nbsp;[Ollama](https://ollama.com) | `http://localhost:11434/v1` | `ollama serve` | Mac, Linux, Windows. |
| <img src="https://github.com/lmstudio-ai.png?size=40" width="20" alt="">&nbsp;[LM Studio](https://lmstudio.ai) | `http://localhost:1234/v1` | `lms server start && lms load <model>` | Mac, Linux, Windows. |
| <img src="https://raw.githubusercontent.com/raullenchai/Rapid-MLX/e2114cf9e7c16dfa3c668832ea6780c02779ca89/docs/assets/logo.png" width="20" alt="">&nbsp;[Rapid-MLX](https://github.com/raullenchai/Rapid-MLX) | `http://localhost:7659/v1` | `rapid-mlx serve <model> --port 8000` | Mac only. The Rapid-MLX Desktop app uses port 7659 and requires the API key; the CLI uses 8000. |
| <img src="https://raw.githubusercontent.com/jundot/omlx/2165e75726ba83d9651dbaced61c97728da77bba/apps/omlx-web/omlx_web/static/favicon.svg" width="20" alt="">&nbsp;[oMLX](https://github.com/jundot/omlx) | `http://localhost:8000/v1` | — | Mac only. Start it from the app or its CLI. Port 8000 comes from third-party sources: check it in oMLX settings. |
| <img src="https://github.com/ml-explore.png?size=40" width="20" alt="">&nbsp;[mlx_lm.server](https://github.com/ml-explore/mlx-lm) | `http://localhost:8080/v1` | `mlx_lm.server --model <model> --port 8080` | Mac only. The reference MLX server, with no extra optimizations. |
| <img src="https://github.com/ggml-org.png?size=40" width="20" alt="">&nbsp;[llama.cpp (llama-server)](https://github.com/ggml-org/llama.cpp) | `http://localhost:8080/v1` | `llama-server -m <file.gguf> --port 8080` | Mac, Linux, Windows. The engine used by Ollama and LM Studio. |
| <img src="https://github.com/vllm-project.png?size=40" width="20" alt="">&nbsp;[vLLM](https://github.com/vllm-project/vllm) | `http://localhost:8000/v1` | `vllm serve <model>` | Linux with NVIDIA/AMD GPU. The most widely used in production. |
| <img src="https://github.com/sgl-project.png?size=40" width="20" alt="">&nbsp;[SGLang](https://github.com/sgl-project/sglang) | `http://localhost:30000/v1` | `python -m sglang.launch_server --model-path <model>` | Linux with NVIDIA/AMD GPU. |
| <img src="https://github.com/lemonade-sdk.png?size=40" width="20" alt="">&nbsp;[Lemonade](https://github.com/lemonade-sdk/lemonade) | `http://localhost:13305/api/v1` | `lemonade-server serve` | Windows/Linux, optimized for AMD Ryzen AI. Older versions use port 8000. |
| <img src="https://github.com/docker.png?size=40" width="20" alt="">&nbsp;[Docker Model Runner](https://docs.docker.com/ai/model-runner/) | `http://localhost:12434/engines/v1` | `docker desktop enable model-runner --tcp 12434` | Mac, Linux, Windows. Host-side TCP access must be enabled. |
| <img src="https://github.com/unslothai.png?size=40" width="20" alt="">&nbsp;[Unsloth Studio](https://github.com/unslothai/unsloth) | `http://localhost:8888/v1` | `unsloth run --model <model>` | Port 8888 comes from examples: «unsloth run» prints the real one at startup. Needs the sk-unsloth-… API key (Studio → Settings → API). |
| <img src="https://github.com/go-skynet.png?size=40" width="20" alt="">&nbsp;[LocalAI](https://github.com/mudler/LocalAI) | `http://localhost:8080/v1` | `local-ai run <model>` | Mac, Linux, Windows. |
| <img src="https://github.com/janhq.png?size=40" width="20" alt="">&nbsp;[Jan](https://github.com/janhq/jan) | `http://localhost:1337/v1` | — | Mac, Linux, Windows. In Jan: Settings → Local API Server → Start. Requires the API key set in Jan. |
| <img src="https://raw.githubusercontent.com/LostRuins/koboldcpp/6d2fedf8624e5f05926af3191f9efdcb13c4133c/niko.ico" width="20" alt="">&nbsp;[KoboldCpp](https://github.com/LostRuins/koboldcpp) | `http://localhost:5001/v1` | `koboldcpp --model <file.gguf>` | Mac, Linux, Windows. |
| <img src="https://raw.githubusercontent.com/oobabooga/textgen/c93f8871239550de2ccfe1e95d469aa82616f07e/css/icon.png" width="20" alt="">&nbsp;[text-generation-webui](https://github.com/oobabooga/textgen) | `http://localhost:5000/v1` | — | Mac, Linux, Windows. Start it with --api. On Mac port 5000 is taken by AirPlay Receiver: use --api-port 5005 and change the URL. |

Notes:
- Several servers share port 8000 or 8080: run one at a time, or change the port with `--port` and update the URL in the app.
- The **API key** field is optional: it is needed for Rapid-MLX Desktop, Jan, Unsloth Studio or vLLM started with `--api-key`. It is never saved or exported.

## Metrics

- **TTFT**: time from sending the request to the first non-empty chunk (content or reasoning).
- **Generation (tok/s)**: (output tokens − 1) / (last token − first token).
- **Effective speed (tok/s)**: output tokens / (last token − request sent).
- **Prompt processing (estimate)**: input tokens / TTFT.
- **RAM**: memory in use on the whole system, sampled every 0.5 s (value before the test and peak).

Tokens come from the `usage` field. If the server does not send it, chunks are counted and an "estimated count" warning appears.

## Presets

- **Short**: short prompt, long answer.
- **Long**: about 8,000 tokens of context, short answer.
- **Cache**: the same long prompt, identical on every run.

In Short and Long every run starts with a unique ID, so prompt caching does not skew the result. Prompts exist in both languages: compare only runs made with the same prompt language (the CSV records it).

The **No reasoning** switch sends a different parameter depending on the server (✅ = tested):
- Ollama: `reasoning_effort: "none"` ✅
- LM Studio: `reasoning_effort: "none"` plus `chat_template_kwargs` ✅
- text-generation-webui: `enable_thinking: false`
- all others (llama.cpp, MLX, vLLM, SGLang…): `chat_template_kwargs: {"enable_thinking": false}`

Some models reason anyway: the app shows a warning in that case.

## Project structure

```
app.py               Streamlit interface
tokenrace/
  bench.py           measuring logic (streaming, timing, RAM, token counts), no Streamlit
  config.py          reads the TOML files
  i18n.py            translations
config/
  servers.toml       preconfigured servers
  defaults.toml      default parameters, timeouts, languages, colours
  prompts.toml       preset prompt texts, per language
locales/
  en.toml, it.toml   interface texts
assets/style.css     visual style
```

**Add a server**: add a `[[server]]` block to `config/servers.toml` and its note under `[server_notes]` in each `locales/*.toml` file.

<a id="languages"></a>**Add a language**: copy `locales/en.toml` to `locales/<code>.toml`, translate it, add the prompt texts in `config/prompts.toml` and the code to `languages` in `config/defaults.toml`.

## Limitations

- RAM is the whole system's, not just the server's.
- Prompt processing speed is an estimate (input tokens / TTFT) and includes network latency and any model loading.
- Default ports for oMLX, Unsloth Studio and text-generation-webui come from examples in their docs: check them when you start the server.

## Contributing

Issues and pull requests are welcome, especially:
- confirmations or fixes for ports and "no reasoning" parameters of servers not yet tested;
- new OpenAI-compatible servers;
- new translations.

## License

[MIT](LICENSE). Server logos belong to their respective projects and are shown only to identify them.
