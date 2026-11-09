# Changelog

## 1.0.0 — 2026-11-10

First public release.

### Added

- Install and run with `uvx tokenrace`, with `--port` and `--lang` options.
- Speed test for local OpenAI-compatible LLM inference servers, with the same client-side measuring code for all: TTFT, generation and effective tokens per second, total time, input and output tokens, estimated prompt speed, system RAM.
- 15 preconfigured servers, including Ollama, LM Studio, Rapid-MLX, oMLX, llama.cpp and vLLM, with editable URL and optional API key.
- Three preset tests: Short, Long (≈8,000 tokens of context) and Cache.
- Reasoning and answer tokens shown separately, and a "No reasoning" switch with the right parameter for each server.
- Streaming response and live metrics, with the status of each run.
- Session summary with median, min and max (cold run excluded from the median), chart per server and model, CSV export.
- English and Italian interface; servers, defaults, prompts and texts in editable TOML files.
- TokenRace logo and mascot.
- Form to share results in GitHub Discussions.
