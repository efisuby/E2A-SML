# PLAN — анализ проекта и работа над выбором языка (GUI + русский анализ)

Дата: 2026-10-18
Статус: в работе (обновляется по мере выполнения)

---

## 1. Что делает проект

**E2A-SML** — инструмент подготовки книги для [ebook2audiobook](https://github.com/efisuby/ebook2audiobook):
он находит в книге реплики и говорящих персонажей, позволяет распределить голоса и
генерирует файл `<book>.e2a.sml.txt` с тегами `[voice:путь/к/голосу]текст[/voice]`.

Поток данных:

```
книга (.txt/.epub/.fb2/...)
  -> convert_ebook_to_txt()            [Calibre ebook-convert, если не .txt]
  -> run_booknlp()                     [sml_extractor/core.py]
       eng -> booknlp/english/EnglishBookNLP (vendored BookNLP: spaCy + BERT coref + quote attribution)
       rus -> booknlp/russian/RussianBookNLP (заглушка, см. баги)
       выход: <id>.tokens, <id>.quotes, <id>.book (JSON), <id>.entities, <id>.book.txt, <id>.characters_simple.json
  -> load_booknlp_output()             [парсит .tokens/.quotes/.entities/.book]
  -> extract_characters() + speaking_characters()
  -> scan_voice_library(root, lang)    [data/voices/{eng|rus}/{age}/{gender}/*.wav]
  -> auto_assign_voices()              [по полу/возраста, с фолбэками]
  -> generate_sml_output()             [токены+реплики -> сегменты по говорящему -> [voice:...]...[/voice]]
```

Точки входа:
* `cli.py` — CLI (`--language eng|rus`, `--model`, `--gui` …) и запуск GUI;
* `web_gui.py` — Gradio 6 GUI (две вкладки: «Книга и скачивание», «Персонажи и голоса»);
* `i18n.py` — словарь переводов `en`/`ru` + `get_text()/set_locale()`;
* `tests/` — unittest (resources, sml_generator, voice_library, web_gui).

Ключевые файлы: `sml_extractor/core.py` (анализ), `sml_extractor/sml_generator.py` (SML),
`sml_extractor/voice_matcher.py` (автоназначение голосов), `booknlp/` (vendored BookNLP).

---

## 2. Найденные баги (со ссылками на код)

### Блокирующие (GUI вообще не работает / русский не работает)

| # | Где | Суть |
|---|-----|------|
| B1 | `sml_extractor/core.py:51,112` | `getattr(booknlp, language)` — имя `booknlp` нигде не импортировано → **NameError** в `check_booknlp_installation()` для любого языка. Кнопка «Создать SML файл» падает сразу; падает и тест `test_missing_resources_get_clear_error`. |
| B2 | `web_gui.py:363..423` | `update_language()`: (а) **не вызывает `set_locale(lang_code)`** — переводы вообще не применяются; (б) возвращает 25 значений при 24 `outputs` → ошибка Gradio; (в) значения привязаны не к тем компонентам (заголовок вкладки в Textbox и т.п.), дубли компонентов в `outputs` (`status_output` ×3, `char_table` ×5, `voice_preview` ×4); (г) обычные строки там, где нужны `gr.update(label=...)`. |
| B3 | `web_gui.py:105,112,127,133` | Язык анализа не передаётся: `check_booknlp_installation()`, `run_booknlp(...)` (4-й позиционный параметр — `language`), `extract_characters(...)`, `scan_voice_library(root)` → GUI **всегда** анализирует как английское и показывает только `voices/eng`. |
| B4 | `booknlp/russian/russian_booknlp.py` | Заглушка: не пишет `.tokens` и `.book`, цикл разметки реплик делает `pass` (`.quotes` остаётся пустым) → для русской книги SML не сгенерируется («No book text data found»), персонажей нет (только Narrator). |
| B5 | `core.py:477`, `sml_extractor/sml_generator.py:275` | `_normalize_name()` вырезает всё кроме `[a-zA-Z0-9\s]` → **все русские имена становятся `Unknown`**, склеиваются в одного персонажа, голоса не назначаются. |
| B6 | `requirements.txt:17` | `ru_core_news_sm>=3.5.0` — этой пакетной версии нет на PyPI (spaCy-модели ставятся веб-колёсами с GitHub releases) → `uv pip install -r requirements.txt` ломается; в `.venv` модели нет. |

### Важные (корректность анализа)

| # | Где | Суть |
|---|-----|------|
| B7 | `core.py:51..64` | Проверка ресурсов (`aliases.txt`, …) для `rus` ищет файлы в `booknlp/russian/data/`, который **пуст**; при этом RussianBookNLP их вообще не использует → для русского всегда «resource files are missing». |
| B8 | `core.py:113` | Финальная проверка импорта всегда делает `from booknlp.booknlp import BookNLP` (англ.) даже для `rus`. |
| B9 | `core.py:390` | `_infer_gender()`: при `char.get("g") is None` — ранний `return "unknown"` **до** русского суффиксового фолбэка; плюс фолбэк читает `char["name"]`, которого в `.book` JSON нет (там `mentions`) → русская инференция пола мертва. |
| B10 | `core.py:361` | `char.get("names", {})` — в `.book` JSON поле называется `mentions` (см. `english_booknlp.py:324`, `sml_generator._build_coref_name_map`) → в фолбэк-пути все персонажи `Character{id}`. |
| B11 | `booknlp/russian/russian_nlp_utils.py:8` | `Path` не импортирован (NameError), `spacy.blank('ru')` без NER → `doc.ents` пуст, entity-теггинг ничего не делает. |
| B12 | `web_gui.py:464` | `set_locale()` вызывается **после** `create_app()` → `E2A_SML_LANG` не влияет на уже собранные надписи; `cli.py:_launch_gui` вообще игнорирует переменную. |

### Косметические / i18n

| # | Где | Суть |
|---|-----|------|
| B13 | `web_gui.py:288,324` | `lang = get_text("app_title")` == `"E2A SML"` всегда → `if lang == "en"` никогда не истинно, подсказка модели всегда `model_info_small`. |
| B14 | `web_gui.py:157,240,251,296` | Захардкоженные английские строки (статус готовности, ошибки «Please process a book first», шапка «Turn an English book…») не переводятся. |
| B15 | `i18n.py` (en-словарь) | Нет ключей `language_selector_label`, `switch_language_info`, `supported_formats_hint` → в EN-UI отображаются сырые имена ключей. |
| B16 | `data/voices/rus/` | Архив с Hub кладёт всего **1** русский голос (`adult/male/Konishev.wav`), остальные категории пустые; `ensure_voice_library()` повторно не качает архив (ENG-голоса уже есть) → большинство персонажей получали «(none)». Код не требовался: библиотека — это локальные данные (`/data/` в `.gitignore`), достаточно положить файлы в `data/voices/rus/{age}/{gender}/`. Сделано: импортировано 40 голосов из локального пака booktts (этап 8e), README обновлён. |

---

## 3. Решения пользователя (согласовано)

1. **Два отдельных селектора в GUI**: «Язык интерфейса» (en/ru) и «Язык книги» (eng/rus) — независимо.
2. **Русский анализ**: эвристический пайплайн **+ BERT-коэрентность (coref) + разметка реплик (quotes)**.
3. `ru_core_news_sm` — **установить** в `.venv` (по URL из `python -m spacy info ru_core_news_sm --url`).

Уточнение по BERT-coref: готовой русской supervised-модели coreference на HF нет
(есть только англ. `biu-nlp/f-coref`, `lingmess-coref` и укр. `artemkramov/coref-ua`).
Поэтому реализуется **BERT-embedding coref**: кандидаты упоминаний (NER + именные
последовательности + местоимения он/она/они/…), контекстные эмбеддинги от
`sentence-transformers/paraphrase-multiniLM` multilingual (BERT-семейство, кэш в
`data/models/booknlp_models/huggingface`), кластеризация близостью + согласование
пола/числа; при недоступности модели — чисто лексический фолбэк. Реплики:
детект кавычек `«…»`, `„…"`, `"…"` + привязка спикера по паттернам
(«сказал X», «X спросил», реплика-тире) с распространением через coref-кластеры.

---

## 4. План работ

| Этап | Содержание | Статус |
|------|-----------|--------|
| 0 | Анализ проекта + этот файл | ✅ |
| 1 | Зависимости: поставить `ru_core_news_sm`, починить `requirements.txt` (URL/комментарий), README | ✅ |
| 2 | `core.py`: NameError (B1), проверка ресурсов по языку (B7), финальный импорт по языку (B8), `mentions` вместо `names` (B10), русский пол до `unknown` (B9), кириллица в `_normalize_name` (B5) | ✅ |
| 3 | `sml_generator.py`: `_normalize_name` — кириллица (B5) | ✅ |
| 4 | Русский пайплайн `booknlp/russian/`: токенизация (spaCy ru, фолбэк-регексп), детект реплик, привязка спикеров, coref (BERT-эмбеддинги + фолбэк), запись `.tokens/.quotes/.book/.entities/.characters_simple.json`; починить `russian_nlp_utils` (B11) | ✅ |
| 5 | GUI: два селектора, рабочая смена языка (`set_locale` + `gr.update(label=...)`, уникальные outputs), язык анализа в `process_book`, i18n всех строк, порядок `set_locale` (B2, B3, B13, B14, B15, B12), недостающие ключи в `i18n.py` | ✅ |
| 6 | CLI: `--ui-language` / чтение `E2A_SML_LANG` до сборки GUI | ✅ |
| 7 | Тесты: смена языка в GUI, русский e2e (синтетический текст → SML), кириллические имена, `check_booknlp_installation('rus')`; починить существующий красный тест | ✅ |
| 8 | Прогон тестов, ручной прогон GUI (ru-UI + русская книга + английская книга), обновление README/Agents.md/PLAN.md | ✅ |

Заметки по объёму B16: автоназначение голосов для `rus` даст максимум 1 голос
(остальным — «(none)», пользователь выберет вручную; библиотеку E2A-Voices не трогаем).

---

## 5. Ход работ (лог)

- [x] этап 0: анализ проекта, `PLAN.md`
- [x] этап 1: `ru_core_news_sm==3.8.0` в `.venv`; `requirements.txt` — PEP 508 direct URL
- [x] этап 2: `sml_extractor/core.py` — B1, B5, B7, B8, B9, B10
- [x] этап 3: `sml_extractor/sml_generator.py` — B5 (кириллица в `_normalize_name`)
- [x] этап 4: `booknlp/russian/` — `russian_nlp_utils.py`, `russian_quotes.py`, `russian_coref.py`, `russian_booknlp.py` (B4, B11); ручной smoke-прогон: все 7 реплик синтетической книги атрибутированы верно, «Иван/Иван Петров/Петров» слились в один кластер, «он» резолвится в Ивана
- [x] этап 5: `web_gui.py` — два селектора, `update_language` на верхнем уровне (20 уникальных outputs, `set_locale` внутри), язык анализа в `process_book` (B2, B3, B12, B13, B14); `i18n.py` — недостающие ключи en/ru синхронизированы (B15)
- [x] этап 6: `cli.py` — `--ui-language`, `E2A_SML_LANG`/`E2A_SML_BOOK_LANG` применяются **до** `create_app()`
- [x] этап 7: тесты — `tests/test_russian_pipeline.py` (e2e, кириллица, coref-конфиг), `tests/test_web_gui.py` (смена языка + язык анализа в `process_book`); всего 25 тестов зелёные
- [x] этап 8a: живой прогон GUI (`--ui-language ru`, `E2A_SML_BOOK_LANG=rus`) — 20 живых обновлений при смене языка EN↔RU через API, русская книга проанализирована end-to-end, персонажи/пол/возраст верные, SML сгенерирован
- [x] этап 8b: по итогам живого прогона найдены и исправлены дефекты русского и английского путей (см. ниже); тесты расширены (26-й кейс: «— …, призналась она.»; 27-й: трансляция кодов языка для `booknlp.BookNLP`)
- [x] этап 8c: живой прогон обеих книг через GUI — `[rus] 8.3s` (Narrator/Татьяна/Сергей; BERT-coref на CPU), `[eng] 9.8s` (Narrator/Martha/Peter, голоса назначены); смена языка EN↔RU живая по 20 обновлений; README/Agents.md/PLAN.md обновлены; всего 27 тестов зелёные
- [x] этап 8d: прогон на GPU (RTX 4060 Ti) — GUI перезапущен без `CUDA_VISIBLE_DEVICES=""`; `SentenceTransformer` выбирает `cuda:0` (632 МиБ резидентно), английская книга даёт 870 МиБ; русский рассказ Куприна end-to-end, английская книга — 3 голоса, смена языка EN↔RU живёт. По ходу найден и исправлен дефект перезагрузки моделей (дефект 7 ниже): повторный русский анализ через GUI 11.3с → **1.84с** (прямой вызов `process()` 6.4с → **0.88с**). Всего 31 тест зелёный.
- [x] этап 8e: расширена русская библиотека голосов (B16) — из локального пака `booktts/voices/voice-pack` импортировано 40 русских голосов (28 м, 12 ж) в `data/voices/rus/adult/{male,female}/`; префикс `RU_Male_`/`RU_Female_` отброшен (каталог уже кодирует язык и пол), возраст — `adult` (в паке не указан), нерусские файлы и `.txt` не копировались. Все 40 файлов проверены `ffprobe` (0 битых), ~98 МиБ. В `data/voices/rus/` теперь 41 голос; живой прогон через GUI: Куприн — 2 реплики/персонажа получили разные голоса из набора, SML ссылается на существующие файлы. Данные локальные (`/data/` в `.gitignore`) — не коммитятся.

### Дефекты, найденные живым прогоном GUI (исправлены)

1. **Реплика обрезалась по «ложному» глаголу.** Сегмент «— Туда, где можно начать
   сначала.» классифицировался как inline-атрибуция из-за стема «нача» в широком списке
   речевых глаголов → span заканчивался на «можно», а «начать сначала.» уходило
   рассказчику. Введён узкий `ATTRIBUTION_VERB_STEMS` / `is_attribution_verb()` для
   распознавания прямой речи vs stage direction; широкий `SPEECH_VERB_STEMS` остался
   для подсказок спикера. (`russian_nlp_utils.py`, `russian_quotes.py`)
2. **`она` отсутствовал в `PRONOUN_GENDER`.** Из-за этого «— …, — призналась она.»
   не получало подсказку (и женские местоимения вообще не резолвились в coref).
   Добавлены `она`, `него`, `неё` (синхронно в `russian_quotes.py` и `russian_coref.py`),
   в широкий список стемов — `призна`, `созна`, `настаива`, `подчерк`, `упомян`,
   `ворч`, `бурч`, `бормот`.
3. **spaCy NER ложно помечал `Пойдём` как PER** → появлялся фиктивный персонаж
   «Пойдём», перетягивавший реплику. Добавлен POS-вето `_has_verb_pos()`: NER/recurring
   кандидат отбрасывается, если spaCy тегирует его как VERB/AUX. (`russian_booknlp.py`)
4. **Off-by-one в диапазоне токенов реплики.** Span, начинающийся между токенами
   (сразу после тире), захватывал само тире. Первый токен теперь ищется по
   перекрытию (`bisect_right(token_ends, span.start)`) — для `.quotes` и `.entities`.
   (`russian_booknlp.py`)
5. **Регрессия английского пути: `BookNLP("eng")`.** Прокидывание книжного языка в
   `run_booknlp()` передавало в вендорный шим `booknlp.BookNLP` код `eng`, а он
   проверяет `language == "en"` → `self.booknlp` не создавался, английский анализ
   падал с `'BookNLP' object has no attribute 'booknlp'`. Теперь `run_booknlp`
   транслирует коды проекта (`eng`/`rus`) в коды пайплайнов (`en`/`rus`).
   Регрессионный тест: `tests/test_booknlp_language_wiring.py`. (`sml_extractor/core.py`)
6. **Обрезанный файл модели (окружение).** В `data/models/booknlp_models/` малая
   coref-модель `coref_google_bert_uncased_L-2_H-256_A-4-v1.0.model` была
   недокачана (12.6 МБ вместо 40.8 МБ, битый zip) — английский анализ с моделью
   `small` падал на загрузке чекпойнта. Файл перекачан с сайта BookNLP и проверен;
   большая модель (`L-12`, 446 МБ) была цела. Это данные, а не код — но проверка
   живого английского прогона её выявила.
7. **Модели перезагружались на каждый запрос (найдено прогоном на GPU).**
   `RussianBookNLP.process()` создавал `RussianCorefResolver()` (→
   `SentenceTransformer(...)`, 4.6–9.6с) и вызывал `spacy.load()` заново при каждом
   анализе книги, поэтому каждый запрос из GUI стоил ~11с независимо от GPU. Введён
   кэш на процесс: `russian_nlp_utils._SPACY_MODEL_CACHE` и
   `russian_coref._MODEL_CACHE` (кэшируется и неудачная загрузка, чтобы офлайн-модель
   не перепробовалась на каждой книге). Эмбеддинг-кэш остался на резолвере — книги
   не делятся векторами. Тесты: `tests/test_russian_pipeline.py::ModelCachingTests`.
   (`russian_nlp_utils.py`, `russian_coref.py`)

---

## 6. Ключевые персонажи + LLM-подбор голосов (итерация 2)

> Историческая итерация: описанный ниже внешний OpenAI-совместимый сервер
> заменён встроенной моделью в §7; механика кастинга, блок-лист голосов
> и `allow_reuse` по-прежнему актуальны.

### 6.1. Что просил пользователь

1. Ключевые персонажи задаются **только через GUI** — многострочное поле,
   свободный текст вставляется как есть (буллеты, описания, заголовки фракций).
2. Голоса подбирает **LLM по короткому описанию** персонажа; в любой момент
   голос можно переопределить вручную в GUI («в моменте»), без жёсткой
   автоматики.
3. Голоса разных персонажей — по возможности разные; дубли только когда
   подходящих голосов не хватает.
4. Убрать из набора выбора **мультяшные/«смешные»** голоса.
5. Если LLM недоступен — тихий откат на текущую эвристику (пол/возраст).
6. Проверка на книге «Ересь Хоруса. 01. Возвышение Хоруса.fb2».

### 6.2. Решения

- LLM — локальный OpenAI-совместимый сервер, по умолчанию
  `http://127.0.0.1:1234/v1` (LM Studio). Env: `E2A_SML_LLM_URL` /
  `E2A_SML_LLM_BASE_URL`, `E2A_SML_LLM_MODEL`, `E2A_SML_LLM_API_KEY`,
  `E2A_SML_LLM_TIMEOUT` (300с), `E2A_SML_LLM_REASONING_EFFORT` (`none`).
- Модель выбирается сама из `/v1/models` по `PREFERRED_MODELS`; embedding-модели
  пропускаются; модель, которая «Failed to load model», модель, ответившая
  прозой, и модель, отвергшая `reasoning_effort`, — перебираются/повторяются.
- Мультяшные голоса вырезаются **блок-листом в коде**
  (`EXCLUDED_VOICE_NAMES` + env `E2A_SML_EXCLUDED_VOICES`); файлы на диске не
  удаляются. Кастомные голоса пользователя не фильтруются.
- Предложения LLM валидируются (голос существует, пол совпадает, дедуп);
  остальным голос добирает детерминированный матчер. `why` показывается только
  для принятого предложения.
- Пол/возраст от LLM заполняют только `unknown`; известные значения не
  перезаписываются. Принудительная атрибуция реплик не делается.
- LLM кастует только верхушку: Narrator + ключевые персонажи + самые «говорящие»
  по числу реплик, максимум `voice_llm.MAX_CAST = 40`. Остальных (в романе их
  сотни) добирает эвристика — иначе JSON-ответ обрезается по `max_tokens` и
  кастинг целиком откатывается.
- `auto_assign_voices(..., allow_reuse=True)`: когда голосов меньше, чем
  персонажей, «лишние» делят уже занятые голоса вместо `(none)`; первым голос
  получают ключевые персонажи (`key_character`), затем известный пол, затем
  остальные. Ключевой персонаж при этом не перетягивает голос у уже
  назначенного.

### 6.3. Файлы

| Файл | Что сделано |
|------|-------------|
| `sml_extractor/llm_client.py` | новый: `LlmClient`, `extract_json`, `get_client`/`reset_client`, `llm_available`, `LlmError` |
| `sml_extractor/character_input.py` | новый: `parse_key_characters` (LLM + regex-фолбэк), `merge_key_characters` |
| `sml_extractor/voice_llm.py` | новый: `assign_voices_with_llm`, `select_cast`, `quote_counts`, `quote_counts` |
| `sml_extractor/voice_matcher.py` | `EXCLUDED_VOICE_NAMES`, `is_voice_excluded()`; фильтрация в `scan_voice_library` / `_pick_unused_voice` |
| `web_gui.py` | поле «Ключевые персонажи», чекбокс «Голоса через LLM», 5-я колонка таблицы (описание/причина), `process_book(..., key_characters_text, use_llm)` |
| `i18n.py` | ru/en строки для новых виджетов и статусов |
| `tests/test_character_input.py`, `tests/test_voice_casting.py` | парсинг/merge, блок-лист, LLM-клиент (retry), кастинг, `select_cast` |

### 6.3.1. Ход работ

- [x] этап 9a: `voice_matcher.py` — блок-лист `EXCLUDED_VOICE_NAMES` + env
- [x] этап 9b: `llm_client.py` — клиент, выбор модели, retries, `extract_json`
- [x] этап 9c: `character_input.py` — LLM-парсинг + regex-фолбэк + `merge_key_characters`
- [x] этап 9d: `voice_llm.py` — кастинг, валидация, детерминированное добивание, `select_cast`
- [x] этап 9e: `web_gui.py` + `i18n.py` — виджеты, таблица, статусы (22 обновления при смене языка)
- [x] этап 9f: тесты — 77 зелёных
- [x] этап 9g: живой прогон на локальной LM Studio (`qwen/qwen3.5-9b`): 11 персонажей → 11 разных голосов, причины на русском
- [x] этап 9h: end-to-end на «Возвышение Хоруса» (654 «говорящих») — каст ограничен 40 персонажами
- [x] этап 9i: README.md, Agents.md, PLAN.md

### 6.4. Исключённые голоса (блок-лист)

`cheburashka`, `cheburashkamovie_2023`, `spoungebob`, `sssr_matroskin`,
`sssr_vinipuh`, `optimusprime`, `johnnysilverhand`, `deadpool`,
`ingridolerinskaya_judy`, `zhirinovsky`, `zadornov (концерт)`, `gorshok`,
`goblin_puchkov`, `druzhko_sergey`, `sergey_chihachev_terminator`,
`aliexpress`, `tinkoff`, `yandexalisa`.

Расширяется через `E2A_SML_EXCLUDED_VOICES=VoiceOne,VoiceTwo`.

---

## 7. Встроенная LLM + эмоции реплик (итерация 3)

### 7.1. Что просил пользователь

1. Определять эмоцию говорящего по каждой реплике небольшой instruct-моделью,
   загружаемой **внутри приложения**, и ставить соответствующие теги в SML.
2. Полностью отказаться от внешнего LLM (LM Studio по HTTP) — встроенная модель
   обслуживает и кастинг голосов, и разбор ключевых персонажей.
3. Локальный E2A (`/home/spell/src/e2a/ebook2audiobook`) пропатчить: научить
   его понимать новые теги.
4. При недоступности модели — тихий откат на эвристику (пайплайн не падает).
5. Проверка на книге «Ересь Хоруса. 01. Возвышение Хоруса.fb2».

### 7.2. Решения

- Новый SML-тег `[emotion:LABEL]…[/emotion]` **внутри** блока голоса:
  `[voice:…][emotion:LABEL]текст[/emotion][/voice]`. `neutral` не пишется
  вообще; нарратив (`Narrator`) не размечается.
- Словарь — 14 меток (`happy, sad, angry, afraid, excited, neutral, mysterious,
  sarcastic, melancholic, energetic, calm, anxious, passionate, playful`);
  русские/английские синонимы нормализуются на метку.
- Модель: `transformers` + `AutoModelForCausalLM`; дефолты `Qwen/Qwen3-1.7B` и
  фолбэк `Qwen/Qwen3-0.6B` (скачиваются с HF при первом использовании),
  `enable_thinking=False`, bfloat16 на CUDA. Env: `E2A_SML_LLM_MODEL`,
  `_DEVICE`, `_DTYPE`, `_MAX_TOKENS`, `_ALLOW_DOWNLOAD`, `_OFF`.
- Разметка эмоций — батчами (`E2A_SML_EMOTION_BATCH`, по умолчанию 24), кэш в
  процессе; ошибка модели или батча → эвристика по словам и пунктуации,
  исключений наружу нет.
- Патч E2A минимальный: `"emotion": {"paired": True}` в `TTS_SML`
  (`lib/conf_models.py`) — от него автоматически расширяются `SML_TAG_PATTERN`,
  защита от перевода и стек парных тегов; в `_convert_sml`
  (`lib/classes/tts_engines/common/utils.py`) ветка `emotion`
  меняет/восстанавливает `fine_tuned_params` и хранит `gain`; в `xtts.py`
  gain применяется к аудио. Таблица оверрайдов `TTS_SML_EMOTIONS`
  (temperature/top_p/speed/gain) — в `lib/conf_models.py`. Движки без
  `fine_tuned_params` принимают тег как no-op.

### 7.3. Файлы

| Файл | Что сделано |
|------|-------------|
| `sml_extractor/llm_client.py` | переписан на in-process `transformers`: `LocalLlmClient`, `chat`/`chat_json`/`unload`, `generator`-хук для тестов; старые имена (`LlmClient`, `llm_available`, `get_client`, `reset_client`, `extract_json`, `LlmError`) сохранены |
| `sml_extractor/emotion.py` | новый: `EMOTION_LABELS`, синонимы, эвристики, `normalize_label`, `analyze_emotions` (батчи/кэш/фолбэк), `analyze_book_emotions` |
| `sml_extractor/sml_generator.py` | `collect_speech_segments`, `_render_segments` с `emotion_map`; мёртвые `_generate_from_tokens`/`_generate_from_book_txt` удалены |
| `web_gui.py` | чекбокс «Размечать эмоции», `process_book(..., label_emotions)`, статус разметки, `emotion_map` в `_session_state`, `unload_model()` после задачи |
| `i18n.py` | ru/en строки виджета, статуса и итога |
| `tests/test_sml_generator.py`, `tests/test_voice_casting.py`, `tests/test_web_gui.py` | теги эмоций, локальный клиент (fake tokenizer/model), интеграция GUI |
| E2A: `lib/conf_models.py`, `lib/classes/tts_engines/common/{headers,utils}.py`, `lib/classes/tts_engines/xtts.py`, `README.md`, `readme/README_rus.md` | сам тег `emotion` и его обработка |

### 7.4. Ход работ

- [x] этап 10a: `llm_client.py` — in-process бэкенд, фолбэк моделей, `unload`
- [x] этап 10b: `emotion.py` — метки, эвристики, батчевый анализ
- [x] этап 10c: `sml_generator.py` — `emotion_map`, `collect_speech_segments`
- [x] этап 10d: `web_gui.py` + `i18n.py` — чекбокс, статус, `unload_model()`
- [x] этап 10e: патч E2A — `TTS_SML['emotion']`, ветка `_convert_sml`, gain в XTTS, README
- [x] этап 10f: тесты — 91 зелёный
- [ ] этап 10g: живой прогон на «Возвышении Хоруса» (первый запуск скачает `Qwen/Qwen3-1.7B`)

### 7.5. Заметка (russian_coref, CPU-retry)

Если GPU занят (например, приложением GUI), BERT-энкодер русской кореференции
падает при загрузке на CUDA и автоматически повторяется на CPU:
`[rus-coref] BERT model '…' could not start on the GPU (CUDA out of memory);
retrying on the CPU.` Это ожидаемо, результат тот же, только медленнее; при
недоступности модели вообще включается лексический фолбэк.
