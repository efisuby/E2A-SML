# E2A-SML: character voices for ebook2audiobook

E2A-SML uses BookNLP to find dialogue and speakers in an **English or Russian** book, lets you assign voices, and creates an SML text file for [ebook2audiobook](https://github.com/efisuby/ebook2audiobook). It runs separately from E2A.

![E2A SML v26.10.1.2 GUI showing the character selector, voice selector, and audio preview](assets/web_gui.png)

## Quick start with Docker

Clone and run E2A-SML on its own:

```bash
git clone https://github.com/efisuby/E2A-SML.git
cd E2A-SML
docker compose up --build
```

Open **http://localhost:7861**. The first start downloads the voice library into `data/`; later starts reuse it. BookNLP models also stay in `data/`. The GUI lets you download the finished SML file from your browser. You may clone this repo into E2A's `components/` folder, but E2A is not required to run the tool.

## Local installation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and use a separate Python 3.10 environment:

```bash
cd E2A-SML
uv venv --python 3.10 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install "$(python -m spacy info en_core_web_sm --url)"
uv pip install "$(python -m spacy info ru_core_news_sm --url)"   # Russian analysis
python cli.py --gui
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` and install the spaCy models with `uv pip install (python -m spacy info en_core_web_sm --url)` (and the same for `ru_core_news_sm`). Native runs download voices into `data/voices/` when needed and store BookNLP models in `data/models/`. Neither the GUI nor CLI needs an Ebook2audiobook path. Install [Calibre](https://calibre-ebook.com/download) to read formats other than `.txt` locally, and make sure `ebook-convert` is on your PATH.

## Make an audiobook with E2A

1. In **Book & Download**, upload a book, pick the **book language** (English/Russian) and select **Create SML file**. Optionally paste the important characters into **Key characters** (see below) and leave **Cast voices with an LLM** and **Label line emotions** ticked. Download the generated `<book>.e2a.sml.txt` file.
2. In **Characters & Voices**, select a character and choose a voice. The preview plays the selected voice, and the SML download updates automatically when you change the voice. The table shows the assigned voice and a short note (the character description or the reason the LLM picked that voice), so you can override any choice.
3. Give that file to E2A as the book input. Library voice tags use paths such as `voices/eng/adult/female/Voice.wav`, relative to E2A's working directory. Run E2A from its project directory and ensure the selected voices exist in its `voices/` folder. Custom voices outside E2A-SML's library retain absolute paths and must be accessible to E2A at those paths.

E2A-SML produces one SML file for E2A. Its voice tags use paths to the assigned voice files.
Each voice tag is closed on the same text line so Calibre can split chapters without breaking E2A's SML parser.

For E2A's macOS command-line launcher, include `--headless` when passing options:

```bash
cd /path/to/ebook2audiobook
./ebook2audiobook.command --headless --tts_engine piper --ebook "/path/to/book.e2a.sml.txt"
```

## Key characters and AI voice casting

**Key characters** is a free-form text box in the GUI (the CLI is unchanged):
paste your cast list exactly as you have it, one character per line, with as
much or as little detail as you like.

```
XVI легион «Лунные Волки»:
• Хорус Луперсий — примарх, Воитель; властный, громовой голос.
• Малогарст («Кривой») — первый капитан, советник Хоруса; хитрый, вкрадчивый.
• Гарвель Локен — капитан 10-й роты, главный герой; честный.
Первый капитан — Севатар.
```

The list guarantees those characters appear in the character table even when
BookNLP missed them, fills in gender/age where they were unknown, and gives the
voice casting something to work with. Nothing is forced on the SML output:
a key character still only speaks where the text attributes a line to them.

With **Cast voices with an LLM** enabled, E2A-SML runs a small instruct model
*inside the app* through `transformers` — there is no external server to start.
The model matches each character to a voice, honouring gender, age and the
description, and keeps voices distinct. The reasons are shown in the table and
every voice can be overridden in the usual picker. When the model cannot be
loaded the tool falls back silently to the gender/age matcher. The same model
also parses the key-character list and labels emotions (below).

The model is fetched from the Hugging Face Hub on first use (about 3.5 GB for
the default) and kept in memory; the GUI unloads it when a book is finished so
E2A has the GPU to itself. Configure it with environment variables (all
optional):

| Variable | Default | Purpose |
|----------|---------|---------|
| `E2A_SML_LLM_MODEL` | `Qwen/Qwen3-1.7B` | Hugging Face repo id or local directory; a comma-separated list is tried in order, falling back to `Qwen/Qwen3-0.6B`. |
| `E2A_SML_LLM_DEVICE` | `auto` | `auto`, `cuda` or `cpu`. |
| `E2A_SML_LLM_DTYPE` | `auto` | `auto`, `bfloat16`, `float16` or `float32` (bfloat16 on CUDA by default). |
| `E2A_SML_LLM_MAX_TOKENS` | `1024` | Answer token budget. |
| `E2A_SML_LLM_ALLOW_DOWNLOAD` | `1` | `0` forbids fetching the model from the Hub; only a cached snapshot or a local path is used. |
| `E2A_SML_LLM_OFF` | – | `1` disables the local model completely (heuristics only). |

Cartoon, comedic/meme, advert and synthetic voices (Cheburashka, SpongeBob,
Zhirinovsky, Deadpool, Yandex Alisa, …) are never offered for automatic
selection. See `EXCLUDED_VOICE_NAMES` in `sml_extractor/voice_matcher.py`; add
your own with `E2A_SML_EXCLUDED_VOICES=VoiceOne,VoiceTwo`.

The LLM and BookNLP share one GPU. A large chat model (12 GB+) leaves no room
for the Russian coreference encoder, which then drops to the lexical heuristic
and produces many junk characters. E2A-SML now retries that encoder on the CPU,
but the fast path is to unload the chat model or pick a smaller one while the
book is being analysed.

## Emotions

Tick **Label line emotions** (on by default) to have the local model tag every
spoken line with the speaker's mood. The line is wrapped in
`[emotion:LABEL]…[/emotion]` inside its voice block:

```
[voice:voices/eng/adult/male/James.wav][emotion:angry]Get out of here![/emotion][/voice]
```

The 14 labels are `happy`, `sad`, `angry`, `afraid`, `excited`, `neutral`,
`mysterious`, `sarcastic`, `melancholic`, `energetic`, `calm`, `anxious`,
`passionate` and `playful`. A plain line is left untagged (`neutral` is never
written), narration is never labelled, and if the model is unavailable the tool
falls back to a small keyword/punctuation heuristic so the pipeline never
fails.

The tag only changes how the patched E2A reads a line — it warms or cools the
XTTS sampling parameters (`temperature`, `top_p`, `speed`) and scales the line's
volume (`gain`); engines without those knobs ignore it. Use the E2A build from
<https://github.com/efisuby/ebook2audiobook>, which adds the `emotion` tag to
`lib/conf_models.py` and the matching branch in
`lib/classes/tts_engines/common/utils.py`. Upstream E2A does not know the tag
and would read it aloud.


## Languages

The GUI has two independent selectors under **Language**:

* **Interface language** (`en`/`ru`) relabels the UI immediately. It can also be set
  at launch with `python cli.py --gui --ui-language ru` or `E2A_SML_LANG=ru`.
* **Book language** (`eng`/`rus`) selects the analysis pipeline and the voice
  library subfolder (`voices/eng` or `voices/rus`). It defaults to the CLI
  `--language` flag, or `E2A_SML_BOOK_LANG`.

Russian analysis runs the vendored heuristic pipeline in `booknlp/russian/`:
spaCy `ru_core_news_sm` tokenization and NER, dialogue detection for `«…»`,
`„…“` and em-dash speech, speaker attribution («сказал Иван», «Иван произнёс:»),
and pronoun coreference with BERT embeddings
(`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, cached under
`data/`). Set `E2A_SML_COREF_MODEL=none` to skip the embedding stage and use the
lexical fallback (nearest preceding mention with matching gender).

The spaCy pipeline and the embedding encoder are loaded once per process and
reused, so analysing several books in one GUI session only pays the load cost
once. With a CUDA build of PyTorch the encoder runs on the GPU automatically
(`SentenceTransformer` picks `cuda:0`); set `CUDA_VISIBLE_DEVICES=""` to force
CPU.

Note: the voice library downloaded from the Hub ships a single Russian voice
(`voices/rus/adult/male/Konishev.wav`), so most Russian characters get *(none)*.
Drop your own files into `data/voices/rus/{age}/{gender}/` (`age` is one of
`child`, `teen`, `adult`, `elder`; `.wav`, `.mp3`, `.flac` and `.ogg` are all
accepted) and they appear in the voice picker on the next analysis — no restart
needed, because the library is rescanned for every book.

## Command line

With the local environment activated, run from the E2A-SML folder:

```bash
python cli.py /path/to/book.txt -o output/
```

Use `python cli.py --help` for model size, custom voice folders, and other options. Book analysis supports English and Russian (`--language eng` or `rus`); the GUI interface language is `--ui-language en|ru`. For non-`.txt` books, install Calibre locally or use Docker.
