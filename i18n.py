"""Internationalization (i18n) support for E2A SML GUI."""

import json
import os


# Default to English
DEFAULT_LANG = "en"

# Translations dictionary: lang_code -> {key: translation}
TRANSLATIONS = {
    # Russian translations
    "ru": {
        # Main app title
        "app_title": "E2A SML",

        # Tab labels
        "tab_book_download": "Книга и скачивание",
        "tab_characters_voices": "Персонажи и голоса",

        # Book & Download tab - UI elements
        "book_file_label": "Файл книги",
        "supported_formats_hint": ".txt, .epub, .mobi, .pdf, .html, .fb2, .azw, .azw3",
        "analysis_model_label": "Модель анализа",
        "model_info_small": "Малая модель — быстрее.",
        "model_info_big": "Большая модель — точнее.",
        "create_sml_button": "Создать SML файл",
        "status_output_label": "Статус",

        # Characters & Voices tab - UI elements
        "characters_voices_intro": "Выберите персонажа и голос. SML для скачивания обновляется автоматически.",
        "character_dropdown_label": "Персонаж",
        "voice_dropdown_label": "Голос",
        "voice_preview_label": "Прослушать голос",

        # Character table headers
        "char_table_header_character": "Персонаж",
        "char_table_header_gender": "Пол",
        "char_table_header_age": "Возраст",
        "char_table_header_assigned_voice": "Присвоенный голос",
        "char_table_header_notes": "Описание / причина",
        "none_voice_placeholder": "(нет)",

        # Key characters and LLM casting
        "key_characters_label": "Ключевые персонажи (необязательно)",
        "key_characters_placeholder": "Хорус Луперкаль — Примарх Лунных Волков, Воитель, властный\nГарвель Локен — капитан 10-й роты, главный герой",
        "key_characters_info": "Вставьте список как есть: по одному персонажу в строке, имя и краткое описание. Пол, возраст и голос подберутся автоматически; пропущенные BookNLP персонажи будут добавлены.",
        "use_llm_label": "Подбирать голоса через LLM",
        "use_llm_info": "Локальная instruct-модель внутри приложения (E2A_SML_LLM_MODEL, по умолчанию Qwen/Qwen3-1.7B). Если она недоступна, используется обычный подбор по полу и возрасту.",
        "status_parsing_characters": "Разбор списка персонажей...",
        "status_llm_casting": "Подбор голосов через LLM...",

        # Emotion labelling
        "analyze_emotions_label": "Размечать эмоции реплик",
        "analyze_emotions_info": "Определять настроение говорящего для каждой реплики и добавлять теги [emotion:…] в SML (требуется локальная модель).",
        "status_emotion_analysis": "Определение эмоций реплик...",
        "success_emotions_msg": "\nЭмоции размечены: реплик — {count}.",

        # Status and informational messages
        "status_preparing": "Подготовка...",
        "status_converting_to_text": "Преобразование в текст...",
        "status_checking_booknlp": "Проверка установки BookNLP...",
        "status_running_booknlp": "Выполнение BookNLP ({model_size} модель) ... Это может занять время.",
        "status_loading_results": "Загрузка результатов...",
        "status_scanning_voice_library": "Сканирование библиотеки голосов...",
        "status_generating_sml": "Генерация SML...",
        "status_done": "Готово!",

        # Download and file labels
        "sml_download_label": "Скачать SML для ebook2audiobook",

        # Error messages
        "error_no_file_selected": "Пожалуйста, загрузите файл книги.",
        "error_voice_library_failed": "Не удалось подготовить библиотеку голосов: {exc}",
        "error_booknlp_not_installed": "BookNLP не установлен правильно:\n{msg}",

        # Success message format
        "success_ready_msg": "Готово к загрузке: {book_id}.e2a.sml.txt\nГоворящих персонажей: {count}; назначено голосов: {num_voices}.",

        # Language selector
        "language_selector_label": "Язык",
        "switch_language_info": "Язык интерфейса программы",
        "ui_language_label": "Язык интерфейса",
        "book_language_label": "Язык книги",

        # App header paragraph
        "app_intro": "Превратите книгу в SML-скрипт для [ebook2audiobook](https://github.com/efisuby/ebook2audiobook).\nПрослушайте и измените голоса персонажей — файл для скачивания обновляется автоматически.",

        # Preview / generation
        "sml_preview_label": "Предпросмотр SML",

        # Error messages (continued)
        "error_process_first": "Сначала обработайте книгу.",
        "error_no_book_text": "Не найден текст книги. Возможно, BookNLP не создал выходные файлы.",
        "error_booknlp_failed": "Ошибка обработки BookNLP: {e}",

        # Accordion labels
        "preview_script_label": "Предпросмотр скрипта",
        "speaking_characters_label": "Все говорящие персонажи",
        "voice_assignments_label": "Присвоения голосов",

        # SML generation status messages
        "sml_generation_ready": "SML готов. Загрузите его выше и откройте в ebook2audiobook.",
        "sml_generation_status": "Скрипт статус",

        # Tab descriptions (info text)
        "book_tab_desc": "Загрузите книгу для обработки BookNLP",
    },

    # English translations (fallback/default)
    "en": {
        "app_title": "E2A SML",
        "tab_book_download": "Book & Download",
        "tab_characters_voices": "Characters & Voices",
        "book_file_label": "Book file",
        "supported_formats_hint": ".txt, .epub, .mobi, .pdf, .html, .fb2, .azw, .azw3",
        "analysis_model_label": "Analysis model",
        "model_info_small": "Small is faster.",
        "model_info_big": "Big is more accurate.",
        "create_sml_button": "Create SML file",
        "status_output_label": "Status",
        "characters_voices_intro": "Choose a character and a voice. The SML download updates automatically.",
        "character_dropdown_label": "Character",
        "voice_dropdown_label": "Voice",
        "voice_preview_label": "Listen to voice",
        "char_table_header_character": "Character",
        "char_table_header_gender": "Gender",
        "char_table_header_age": "Age",
        "char_table_header_assigned_voice": "Assigned Voice",
        "char_table_header_notes": "Notes / reason",
        "none_voice_placeholder": "(none)",

        # Key characters
        "key_characters_label": "Key characters (optional)",
        "key_characters_placeholder": "Horus Lupercal — Warmaster, primarch of the Luna Wolves, commanding\nGarviel Loken — captain of the 10th company, main protagonist",
        "key_characters_info": "Paste your notes as-is: a name and a short description, one character per line. Characters BookNLP missed are added and voice casting uses the descriptions.",
        "use_llm_label": "Cast voices with an LLM",
        "use_llm_info": "In-process instruct model (E2A_SML_LLM_MODEL, default Qwen/Qwen3-1.7B). When unavailable, the plain gender/age matcher is used.",
        "status_parsing_characters": "Parsing the key-character list...",
        "status_llm_casting": "Casting voices with the LLM...",

        # Emotion labelling
        "analyze_emotions_label": "Label line emotions",
        "analyze_emotions_info": "Detect the speaker's mood for every line and add [emotion:…] tags to the SML (requires the local model).",
        "status_emotion_analysis": "Detecting line emotions...",
        "success_emotions_msg": "\nLabeled emotions: {count} lines.",
        "status_preparing": "Preparing...",
        "status_converting_to_text": "Converting to text...",
        "status_checking_booknlp": "Checking BookNLP installation...",
        "status_running_booknlp": "Running BookNLP ({model_size} model)... This may take a while.",
        "status_loading_results": "Loading results...",
        "status_scanning_voice_library": "Scanning voice library...",
        "status_generating_sml": "Generating SML...",
        "status_done": "Done!",
        "error_no_file_selected": "Please upload a book file.",
        "error_voice_library_failed": "Unable to prepare the voice library: {exc}",
        "error_booknlp_not_installed": "BookNLP is not properly installed:\n{msg}",
        "success_ready_msg": "Ready to download: {book_id}.e2a.sml.txt\nSpeaking characters: {count}; voices assigned: {num_voices}.",

        # Language selector
        "language_selector_label": "Language",
        "switch_language_info": "Interface language of this app",
        "ui_language_label": "Interface language",
        "book_language_label": "Book language",

        # App header paragraph
        "app_intro": "Turn a book into an SML script for [ebook2audiobook](https://github.com/efisuby/ebook2audiobook).\nPreview or change character voices — the download updates automatically.",

        # Download and file labels
        "sml_download_label": "Download SML for ebook2audiobook",

        # Preview / generation
        "sml_preview_label": "SML preview",

        # Error messages (continued)
        "error_process_first": "Please process a book first.",
        "error_no_book_text": "No book text data found. BookNLP may not have generated output files.",
        "error_booknlp_failed": "BookNLP processing failed: {e}",

        "preview_script_label": "Preview script",
        "speaking_characters_label": "All speaking characters",
        "voice_assignments_label": "Voice assignments",
        "sml_generation_ready": "SML is ready. Download it above and open it in ebook2audiobook.",
        "sml_generation_status": "Script status",
        "book_tab_desc": "Upload a book for BookNLP processing",
    },
}


def get_locale():
    """Get the current locale from environment or session, defaulting to Russian.

    Returns:
        Language code ('ru' for Russian or 'en' for English)
    """
    # Check if user has selected Russian - prefer GUI selection over env var
    # Users who want Russian should have it enabled via environment variable
    env_lang = os.environ.get("E2A_SML_LANG", "").lower()

    # Default to English (original behavior for backward compatibility)
    # If you want Russian by default, change DEFAULT_LANG to 'ru' or add:
    # if not env_lang and DEFAULT_LANG == 'en':  # was ru before
    #     return 'ru'

    if env_lang in TRANSLATIONS:
        return env_lang

    # Fallback to English
    return DEFAULT_LANG


def get_text(key, **kwargs):
    """Get a translated string for the current locale.

    Args:
        key: Translation key (e.g., "tab_book_download")
        **kwargs: Arguments for string formatting (e.g., {count}, {exc})

    Returns:
        Translated string or English fallback if translation not found.
    """
    lang = get_locale()
    translations = TRANSLATIONS.get(lang, TRANSLATIONS["en"])

    try:
        text = translations[key]
        # Apply formatting if kwargs provided
        if kwargs:
            return text.format(**kwargs)
        return text
    except KeyError:
        # Fallback to English for missing keys
        en_text = TRANSLATIONS.get("en", {}).get(key, key)
        return en_text


def set_locale(lang_code):
    """Set the locale (for use by web GUI via session state).

    Args:
        lang_code: Language code ('ru' or 'en')

    Returns:
        The previously active locale
    """
    previous = get_locale()
    os.environ["E2A_SML_LANG"] = lang_code
    return previous


def init_i18n():
    """Initialize i18n system. Returns current locale."""
    return get_locale()
