# Changelog

## 1.0.2 — 2026-11-12

### Added

- Answer TTFT and visible speed (tok/s): time to the first token of the visible answer and answer tokens / (last token − request sent). Shown after each run when the model reasons, in the summary (median, min, max) and as two new columns at the end of the CSV. Existing metrics and CSV columns are unchanged.

### Changed

- TTFT help text now says it includes reasoning.

## 1.0.1 — 2026-11-10

### Fixed

- With "No reasoning" off, servers with a tested parameter (Rapid-MLX, oMLX, LM Studio) are now asked for reasoning explicitly, so they all run in the same mode. Rapid-MLX turns reasoning off when a request states no preference ([Rapid-MLX#5691](https://github.com/raullenchai/Rapid-MLX/issues/5691)). Ollama keeps its default, and untested servers get no extra field.
- Rapid-MLX marked as tested for the "No reasoning" parameter.
- README: removed the "reasoning on" columns from the example results until they are re-measured, and corrected the note on Rapid-MLX.

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
