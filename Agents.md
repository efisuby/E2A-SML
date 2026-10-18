# E2A-SML: Agents Documentation

This document summarizes the architecture, implementation details, and pending work for agents working on **E2A-SML** (English/Russian book analysis + SML voice assignments for ebook2audiobook). It captures design decisions, current capabilities, language-specific dependencies, and how to extend the system.

---

## 1. System Overview

### Purpose
E2A-SML is a character-voice assignment tool for **ebook2audiobook**. Given an English or Russian book, it:

1. Uses **BookNLP** (an internal NLP library) to identify dialogue speakers and characters in the text.
2. Lets users assign or auto-assign voices from a voice library.
3. Produces an **SML** file that ebook2audiobook uses for multi-speaker TTS generation.

### High-Level Architecture

```
+-------------------+       +------------------------+       +---------------------+
|   Book Input      | ----> |  BookNLP (analysis)    | ----> |  Voice Assignments |
| (.txt, .epub, ...)│       | - entity recognition   │       |  & SML Generator   │
+-------------------+       | - quote tagging         │       +--------+----------+
                            | - supersense             │               |
                            | - event detection        │               v
                            +--------------------------+      +-------+------+
                                                             |  ebook2audiobook |
                                                             | (TTS engine)    |
                                                             +--------+--------+
                                                                      |
                                                                      v
                                                               SML File for TTS
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Vendored BookNLP** | BookNLP is a custom NLP library that uses spaCy models internally. Vendoring avoids dependency conflicts with the main E2A codebase and provides full control over model loading and caching. |
| **Language-specific modules** | Separate `booknlp/english/` and `booknlp/russian/` directories contain language-specific logic while sharing common infrastructure (e.g., voice library, SML generator). Both write the same BookNLP-compatible output files. |
| **Portable paths for voices** | Voice assignments use relative paths (`voices/{lang}/{age}/{gender}/...`) to work within E2A's working directory, or absolute paths when voices are outside the standard location. |
| **Session-based GUI state** | The Gradio web interface uses `_session_state` dictionary to persist book data, voice assignments, and character selections between callbacks without global singletons. |

---

## 2. Project Structure

### Top-Level Files

| Path | Description |
|------|-------------|
| `cli.py` | Command-line interface with argument parsing for input file, output directory, model size, language selection (`eng`/`rus`), and GUI mode. Handles BookNLP installation checks, SML generation via `portable_voice_assignments()`, and delegates to `_run_headless()` or `_launch_gui()`. |
| `README.md` | User-facing documentation with quick-start instructions (Docker, local install) and example commands. |
| `requirements.txt` | Python dependencies including spaCy models for English and Russian (`en_core_web_sm`, `ru_core_news_sm`). |
| `web_gui.py` | Gradio-based web interface that provides a character selector, voice selector with audio preview, and live SML update when voices are changed. |
| `VERSION.txt` | Current version number (e.g., `26.10.1.2`). |

### Core Modules in `sml_extractor/`

| Module | Responsibilities |
|--------|-----------------|
| `core.py` | - `configure_booknlp_cache()`: sets `HF_HOME` to this tool's data directory for model caching.<br>- `check_booknlp_installation(language)`: verifies BookNLP and spaCy models for English or Russian are installed.<br>- `convert_ebook_to_txt()`: uses Calibre's `ebook-convert` to transform non-text files to `.txt`.<br>- `run_booknlp(input_file, output_dir, model_size, language)`: orchestrates the BookNLP pipeline; calls `BookNLP(language, model_params)` and invokes `process()` on the input file.<br>- `extract_characters(booknlp_data, language)`: builds a character list from `.book` JSON data; uses `_infer_gender()`, `_infer_age()`, and `_normalize_name()` for inference.<br>- `load_booknlp_output(output_dir, book_id)`: parses `.tokens`, `.quotes`, `.entities`, `.book` JSON files into a structured dict. |
| `sml_generator.py` | - `resolve_voice_path()`: resolves voice paths relative to the library root.<br>- `portable_voice_assignments()`: converts absolute paths to E2A-relative or absolute for custom voices.<br>- `collect_speech_segments(booknlp_data)`: returns the ordered `(speaker, cleaned_text)` pairs the writer emits (the keys an `emotion_map` is built from).<br>- `_book_segments()` / `_segments_from_tokens()` / `_segments_from_book_txt()`: build the raw `(speaker, text)` segments at token-level quote boundaries (preferred) or from the sentence-level `.book.txt`; a `None` speaker marks a paragraph break.<br>- `_render_segments()`: emits `[voice:…][emotion:LABEL]text[/emotion][/voice]` (emotion only when `emotion_map` has the cleaned text).<br>- `generate_sml_output(..., emotion_map=None)`: main entry point that writes `.e2a.sml.txt` with embedded voice and emotion tags. |
| `voice_library.py` | - `ensure_voice_library()` downloads voices from Hugging Face (`ebook2audiobook/E2A-Voices`) if the local library is missing.<br>- `_safe_extract()`: safely extracts ZIP archives while preventing path traversal attacks. |
| `voice_matcher.py` | Implements auto-assignment logic: known-gender characters get matching voices first; unknown-gender characters are alternated between male and female pools to avoid exhausting one gender's supply. Falls back across age categories when exact matches aren't available. Also holds `EXCLUDED_VOICE_NAMES` / `is_voice_excluded()` — cartoon, comedic/meme, advert and synthetic voices that `scan_voice_library()` and `_pick_unused_voice()` skip (extend with `E2A_SML_EXCLUDED_VOICES`). |
| `llm_client.py` | Optional **in-process** instruct model loaded with `transformers` (`AutoModelForCausalLM` + `AutoTokenizer`). `LocalLlmClient` lazily loads the first usable model from `model_candidates()` (`E2A_SML_LLM_MODEL`, default `Qwen/Qwen3-1.7B` then `Qwen/Qwen3-0.6B`), keeps it resident, disables thinking (`enable_thinking=False`), strips a stray ` thinking` block, and `unload()` frees VRAM. `chat_json()` = `extract_json(chat(...))`; `extract_json()` tolerates ```json fences/prose. `llm_available()` is the cheap probe (no load); a `generator=(system, user, budget)->str` hook lets tests run without a GPU. Public aliases kept: `LlmClient = LocalLlmClient`, `LlmError`, `get_client`, `reset_client`, `unload_model`. Env: `E2A_SML_LLM_MODEL`, `_DEVICE`, `_DTYPE`, `_MAX_TOKENS`, `_ALLOW_DOWNLOAD`, `_OFF`. No external server. |
| `emotion.py` | Speaker-emotion labelling for a line. `EMOTION_LABELS` (14) + `_SYNONYMS` (ru/en); `normalize_label()`/`heuristic_emotion()` map a model answer or the raw text onto a label; `analyze_emotions(texts)` batches lines (`E2A_SML_EMOTION_BATCH`, default 24) through the local LLM with an in-process cache and a per-batch heuristic fallback that never raises; `analyze_book_emotions(segments)` labels only non-`Narrator` dialogue and returns a `{cleaned_text: label}` map without `neutral`. Feeds `generate_sml_output(emotion_map=…)`. |
| `character_input.py` | Parses the GUI's free-form key-character notes into `{name, aliases, gender, age, description}` (LLM first, regex fallback), and `merge_key_characters()` links them to BookNLP clusters one-to-one by scored name matching (exact > word-boundary prefix/suffix) so Horus/Хорус Аксиманд never collapse into one row. |
| `voice_llm.py` | LLM-assisted casting: lists characters (with descriptions) and available voices, parses the JSON proposal, rejects unknown voices and gender mismatches, keeps voices distinct, and deterministically fills any gaps with `_find_best_voice()`. Returns `(assignments, reasons)`; an empty result means "LLM unavailable → use `auto_assign_voices()`". |

### Data Directory (`data/`)
- `models/booknlp_models/` – Hugging Face cache for BookNLP spaCy models
- `voices/` – Voice library downloaded from Hugging Face (organized as `voices/{lang}/{age}/{gender}/...`)

---

## 3. Language-Specific Implementation Details

### English Support

English support is complete and relies on:

| Component | Details |
|-----------|---------|
| **spaCy model** | `en_core_web_sm` (Small model, ~40 MB) loaded by BookNLP for entity recognition and gender inference. |
| **BookNLP module** | `booknlp/english/` contains the vendored spaCy model loading logic specific to English. |

The current implementation uses the `.tokens` file from BookNLP output to build segments of consecutive same-speaker text, giving precise quote boundaries for voice switching.

### Russian Support (Implemented)

Russian analysis lives in `booknlp/russian/` and writes the same output files as
the English pipeline (`.tokens`, `.quotes`, `.entities`, `.book`,
`.characters_simple.json`), so `sml_extractor` consumes either language without
special cases:

| Module | Responsibilities |
|--------|------------------|
| `russian_booknlp.py` | `RussianBookNLP.process()`: orchestration — tokenization, name-mention discovery (NER + recurring capitalized sequences + attribution names), union-find clustering of name surfaces sharing a word (`Иван` / `Иван Петров` / `Петров`), dialogue attribution, pronoun resolution, character assembly, and BookNLP-compatible output writing. |
| `russian_quotes.py` | Dialogue span detection (`«…»`, `„…“`, `“…”`, ASCII quotes, em-dash speech with sentence-boundary checks) and speaker hints («сказал Иван», «Иван сказал», «сказал он», «Иван произнёс:», «Иван:»). Attribution windows are cut at the first/last sentence boundary so neighbouring sentences cannot leak a false name. |
| `russian_coref.py` | Pronoun coreference: BERT embeddings via `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (gender agreement filter + cosine + recency bonus, `SIMILARITY_FLOOR=0.45`); lexical fallback (nearest preceding mention of matching gender) when the model is missing/offline or `E2A_SML_COREF_MODEL=none`. The encoder is cached process-wide in `_MODEL_CACHE` (keyed by model name, failures included), while the embedding cache stays per resolver so books never share vectors. On a CUDA build `SentenceTransformer` picks `cuda:0` automatically (embedding batches are tiny, so the GPU mainly helps by keeping the encoder warm); a CUDA failure (a local LLM holding the card is the usual cause) is retried with `device="cpu"` before the lexical fallback is used, because the lexical path produces many junk "characters" on a novel. |
| `russian_nlp_utils.py` | `ru_core_news_sm` loader (regex fallback when absent; the loaded pipeline is cached in `_SPACY_MODEL_CACHE` because it is stateless and re-loaded on every `process()` otherwise), speech-verb stems for attribution patterns, Cyrillic normalization. |

Supporting rules in `sml_extractor/core.py`: `_infer_gender()` falls back to
Russian suffix/name tables (`_RU_FEMALE_SUFFIXES`, `_RU_MALE_NAMES`, …) before
returning `unknown`; `_infer_age()` reads Russian age terms; `_normalize_name()`
keeps Cyrillic.

GUI: `web_gui.py` has two independent selectors — interface language
(`en`/`ru`, switched live through `update_language()` + `set_locale()`) and
book language (`eng`/`rus`, threaded into `check_booknlp_installation()`,
`run_booknlp()`, `extract_characters()`, `scan_voice_library()`).

### Key characters, LLM voice casting and emotions (GUI only)

`process_book(input_file, model_size, book_language, key_characters_text,
use_llm, label_emotions)` probes the local model once (`llm_available()`) and
then:

1. runs BookNLP and `speaking_characters()`;
2. parses the pasted notes (`parse_key_characters()`, LLM or regex) and merges
   them with `merge_key_characters()` — key characters are guaranteed a row
   even with zero attributed quotes, which is why the merge happens *after*
   `speaking_characters()`;
3. casts voices with `assign_voices_with_llm()` when the model answered,
   otherwise with `auto_assign_voices()`;
4. when **Label line emotions** is ticked, clears the emotion cache, calls
   `collect_speech_segments()` + `analyze_book_emotions()` and stores the
   `{cleaned_text: label}` map in `_session_state['emotion_map']` (any failure is
   caught and logged, leaving the SML untagged);
5. fills the fifth table column (description + casting reason) for the manual
   voice picker, then calls `unload_model()` so the GPU is free while E2A runs.

The SML output keeps its shape: a key character only gets `[voice:…]` tags on
lines the token/quote data attributes to that name, and an `[emotion:…]` tag is
added only around a labelled non-narrator line. `generate_output()` (and
therefore `reassign_voice()`) passes `_session_state['emotion_map']` on every
regeneration, so cached labels survive a voice change without re-running the
model. `_session_state` also carries `voice_reasons` for the table;
`_build_character_table()` and `reassign_voice()` both read it. New `i18n.py`
keys: `key_characters_label/_placeholder/_info`, `use_llm_label`, `use_llm_info`,
`analyze_emotions_label/_info`, `status_parsing_characters`,
`status_llm_casting`, `status_emotion_analysis`, `success_emotions_msg`,
`char_table_header_notes`. `update_language()` now returns 23 updates — keep it
in sync with the `ui_lang.change(outputs=[…])` list in `create_app()`.

---

## 4. Implementation Patterns and Conventions

### Common Functions Across Modules

- **Path resolution**: All voice paths are resolved relative to `configured_library_root()` (which reads `SML_DATA_DIR` environment variable or defaults to `data/`).
- **Progress callbacks**: Headless CLI mode uses a `progress_callback(message, pct)` function for percentage-based progress updates; GUI mode uses Gradio's built-in progress bar.
- **Error handling**: Installation checks (`check_booknlp_installation()`) return `(bool, str)` tuples so failures can be communicated gracefully via CLI error messages or GUI status boxes.

### SML Generation Patterns

The system prefers token-level quote boundaries over sentence-level output to ensure voice switches occur at exact quote edges. It falls back to `.book.txt` (sentence-level) only when token data is missing. Voice tags use:
- **Macro references** (`[voice:{name}]`) if `use_macros=True`, or
- **Absolute/relative paths** (`[voice:/path/to/voice.wav]`) for direct TTS engine input.

A labelled spoken line is additionally wrapped as
`[voice:…][emotion:LABEL]text[/emotion][/voice]`; the emotion tag is nested
inside the voice block, omitted for `neutral`/narration, and ignored by E2A
engines that lack `fine_tuned_params`.

---

## 5. Pending Work Summary

| Task | Status | Notes |
|------|--------|-------|
| **Create `booknlp/russian/` module** | Done | Heuristic pipeline + BERT-embedding coref; covered by `tests/test_russian_pipeline.py`. |
| **Russian gender inference** | Done | Suffix/name tables in `core.py`, applied before `unknown`. |
| **Russian age inference** | Done | Russian age terms in `russian_booknlp._age_for_cluster()` + `core.py`; defaults to `adult`. |
| **GUI language selectors** | Done | Interface language (en/ru) and book language (eng/rus) are independent; `--ui-language` / `E2A_SML_LANG` / `E2A_SML_BOOK_LANG` set defaults. |
| **GUI testing with Russian books** | Partial | Covered end-to-end by unit tests on synthetic text; manual GUI runs still the release step. |
| **Russian voice library coverage** | Works locally | The Hub archive ships one Russian voice (`rus/adult/male/Konishev.wav`). Voices are local data (`/data/` is gitignored): this checkout was extended with 40 Russian voices in `data/voices/rus/adult/{male,female}/`, so characters get distinct voices. Add more by dropping files into `data/voices/rus/{age}/{gender}/`; the library is rescanned on every `process_book` call, so no restart is needed. Mixing `.wav`/`.mp3` is fine (`VOICE_EXTENSIONS`), and the per-language `default.txt` is the reference transcript — per-voice `.txt` files are not used. |
| **Key characters from free text** | Done | GUI text box → `character_input.parse_key_characters()` (LLM, regex fallback) → `merge_key_characters()`; covered by `tests/test_character_input.py`. |
| **LLM voice casting** | Done | `llm_client.py` + `voice_llm.py`; silent fallback to `auto_assign_voices()`; covered by `tests/test_voice_casting.py`. Casting now uses the in-process model (no external server). |
| **In-process LLM backend** | Done | `llm_client.py` rewritten from the OpenAI-compatible HTTP client to `transformers`: `LocalLlmClient` lazily loads/serves/unloads `E2A_SML_LLM_MODEL` (default `Qwen/Qwen3-1.7B` → `Qwen/Qwen3-0.6B`), with a `generator=` test hook; the old public names are kept as aliases. |
| **Speaker emotion labels** | Done | `emotion.py` labels non-narrator lines (local model, batched, heuristic fallback) and the SML writer wraps them in `[emotion:LABEL]` inside the voice block; GUI checkbox `Label line emotions`. Needs the patched E2A fork (`TTS_SML['emotion']`, `_convert_sml` emotion branch, XTTS volume gain). Covered by `tests/test_sml_generator.py` and `tests/test_web_gui.py`. |
| **Cartoon/meme voice filter** | Done | `EXCLUDED_VOICE_NAMES` in `voice_matcher.py`; `E2A_SML_EXCLUDED_VOICES` extends it. |

---

## 6. Example Usage

### CLI (English)
```bash
uv pip install -r requirements.txt
python cli.py input_book.txt -o output/ --model big
# Russian book:
python cli.py book.txt --language rus
```

### CLI (with existing BookNLP output)
```bash
python cli.py --booknlp-dir /path/to/booknlp_output --book-id mybook -o sml_output/
```

### Web GUI
```bash
python web_gui.py
# or from CLI: python cli.py --gui
# Russian interface, Russian book defaults:
python cli.py --gui --ui-language ru --language rus
```

---

## 7. Notes for Future Agents

- **BookNLP uses vendored spaCy models** – ensure the `data/models/booknlp_models/` cache directory exists and is writable; models are downloaded there on first use. Downloads are only skipped when the file already exists, so a truncated `.model` file stays broken forever — verify with `zipfile.is_zipfile` if a checkpoint fails to load.
- **Language codes**: the project uses `eng`/`rus`; `run_booknlp()` translates them to the pipeline codes (`en` for the vendored `booknlp.BookNLP`, `rus` for `RussianBookNLP`). The shim only builds a pipeline when `language == "en"`, so passing `eng` through silently yields `'BookNLP' object has no attribute 'booknlp'`.
- **Russian support** is implemented in `booknlp/russian/` (see §3); extend attribution patterns in `russian_quotes.py` rather than adding language branches elsewhere — `russian_booknlp.py` already writes BookNLP-compatible files, so `sml_extractor` needs no language-specific code paths. Two distinct verb sets live in `russian_nlp_utils.py`: `SPEECH_VERB_STEMS` (broad, for speaker hints) and `ATTRIBUTION_VERB_STEMS` (narrow, decides whether a dash segment is stage direction). Keep them separate: broad verbs such as «начать»/«думать» appear *inside* utterances and would truncate them.
- **Voice library paths** are relative to `data/voices/` by default; custom voices can point to any accessible path but must exist at runtime for TTS engines to find them.

---

*Generated with [Claude Code](https://claude.com/claude-code)*
