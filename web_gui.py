#!/usr/bin/env python3
"""Web GUI for SML Book Dialog Extractor using Gradio with i18n support."""

import os
import tempfile
from sml_extractor.core import configure_booknlp_cache
if 'HF_HOME' not in os.environ:
    configure_booknlp_cache()
import gradio as gr

from sml_extractor.character_input import merge_key_characters, parse_key_characters
from sml_extractor.core import (
    check_booknlp_installation,
    convert_ebook_to_txt,
    extract_characters,
    load_booknlp_output,
    run_booknlp,
)
from sml_extractor.emotion import analyze_book_emotions, clear_cache
from sml_extractor.llm_client import llm_available, unload_model
from sml_extractor.sml_generator import (
    collect_speech_segments,
    generate_sml_output,
    portable_voice_assignments,
    resolve_voice_path,
    speaking_characters,
)
from sml_extractor.voice_library import configured_library_root, ensure_voice_library
from sml_extractor.voice_llm import assign_voices_with_llm, quote_counts
from sml_extractor.voice_matcher import (
    auto_assign_voices,
    get_voice_category_info,
    get_voice_display_name,
    scan_voice_library,
)

# Import i18n module for internationalization
from i18n import TRANSLATIONS, get_locale, get_text, set_locale


# Global state for the current session
_session_state = {}
APP_CSS = ".gradio-container { max-width: 980px !important; margin-inline: auto !important; }"


def _get_file_path(file_obj) -> str:
    """Extract file path from a Gradio file object or string."""
    return file_obj.name if hasattr(file_obj, "name") else str(file_obj)


def _get_all_voice_paths(voice_library: dict) -> list:
    """Collect all voice file paths from the voice library into a flat list."""
    paths = []
    for age in voice_library:
        for gender in voice_library.get(age, {}):
            paths.extend(voice_library[age][gender])
    return sorted(paths)


def _voice_display_label(voice_path: str) -> str:
    """Create a human-readable label from a voice path, e.g. 'AlexandraHisakawa (adult/female)'."""
    info = get_voice_category_info(voice_path)
    name = info["name"]
    age = info["age"]
    gender = info["gender"]
    if age != "unknown" and gender != "unknown":
        return f"{name} ({age}/{gender})"
    return name


def preview_voice(voice_path: str | None) -> str | None:
    """Return the selected library voice for the browser's audio player."""
    if not voice_path:
        return None
    library_root = str(_session_state.get('library_root', configured_library_root()))
    absolute_path = resolve_voice_path(voice_path, library_root)
    return str(absolute_path) if absolute_path.is_file() else None


def process_book(
    input_file: str | None,
    model_size: str,
    book_language: str = "eng",
    key_characters_text: str = "",
    use_llm: bool = True,
    label_emotions: bool = True,
    progress: gr.Progress = gr.Progress(),
) -> tuple[object, ...]:
    """Process a book file through BookNLP and extract characters."""
    if input_file is None:
        raise gr.Error(get_text("error_no_file_selected"))

    language = book_language if book_language in ("eng", "rus") else "eng"

    # Probe the optional LLM once: it drives both the key-character parsing
    # and the voice casting, and is skipped entirely when unreachable.
    llm_ready = bool(use_llm) and llm_available()

    library_root = str(configured_library_root())
    try:
        ensure_voice_library(library_root)
    except Exception as exc:
        raise gr.Error(get_text("error_voice_library_failed", exc=str(exc))) from exc

    progress(0.05, desc=get_text("status_preparing"))

    # Create temp working directory
    work_dir = tempfile.mkdtemp(prefix="sml_extractor_")
    _session_state["work_dir"] = work_dir
    _session_state["generation"] = 0

    input_path = _get_file_path(input_file)

    # Convert to txt if needed
    progress(0.1, desc=get_text("status_converting_to_text"))
    try:
        txt_path = convert_ebook_to_txt(input_path, work_dir)
    except RuntimeError as e:
        raise gr.Error(str(e))

    # Run BookNLP
    booknlp_dir = os.path.join(work_dir, "booknlp")
    progress(0.12, desc=get_text("status_checking_booknlp"))

    ok, msg = check_booknlp_installation(language)
    if not ok:
        raise gr.Error(get_text("error_booknlp_not_installed", msg=msg))

    progress(0.15, desc=get_text("status_running_booknlp", model_size=model_size))

    try:
        result = run_booknlp(
            txt_path, booknlp_dir, model_size, language, data_root=library_root
        )
    except Exception as e:
        raise gr.Error(get_text("error_booknlp_failed", e=str(e)))

    book_id = result["book_id"]
    _session_state["book_id"] = book_id
    _session_state["booknlp_dir"] = booknlp_dir
    _session_state["language"] = language

    progress(0.6, desc=get_text("status_loading_results"))

    # Load data
    booknlp_data = load_booknlp_output(booknlp_dir, book_id)
    _session_state["booknlp_data"] = booknlp_data

    # Extract characters
    characters = speaking_characters(
        booknlp_data, extract_characters(booknlp_data, language)
    )

    # Merge the explicit key-character list so the named cast is always
    # present, carries a description, and gets cast a voice.
    key_text = (key_characters_text or "").strip()
    if key_text:
        progress(0.66, desc=get_text("status_parsing_characters"))
        key_characters = parse_key_characters(key_text, use_llm=llm_ready)
        characters = merge_key_characters(characters, key_characters)
    _session_state["characters"] = characters

    progress(0.7, desc=get_text("status_scanning_voice_library"))

    # Scan this tool's voice library for the book language
    voice_library = scan_voice_library(library_root, language)
    _session_state["voice_library"] = voice_library
    _session_state["library_root"] = library_root

    # Assign voices: the LLM casts from descriptions/names when available,
    # otherwise the deterministic gender/age matcher runs.
    voice_assignments = {}
    voice_reasons = {}
    if voice_library:
        if llm_ready:
            progress(0.75, desc=get_text("status_llm_casting"))
            try:
                voice_assignments, voice_reasons = assign_voices_with_llm(
                    characters,
                    voice_library,
                    language=language,
                    counts=quote_counts(booknlp_data),
                )
            except Exception:
                voice_assignments, voice_reasons = {}, {}
        if not voice_assignments:
            voice_assignments = auto_assign_voices(characters, voice_library)
            voice_reasons = {}
    _session_state["voice_assignments"] = voice_assignments
    _session_state["voice_reasons"] = voice_reasons

    # Label the emotion of every spoken line with the local model.  This is
    # best-effort: a failure only means the SML keeps its untagged lines.
    clear_cache()
    emotion_map = {}
    if label_emotions and llm_ready:
        progress(0.8, desc=get_text("status_emotion_analysis"))
        try:
            segments = collect_speech_segments(booknlp_data)
            emotion_map = analyze_book_emotions(
                segments,
                progress=lambda frac, desc=None: progress(
                    0.8 + 0.08 * frac,
                    desc=desc or get_text("status_emotion_analysis"),
                ),
            )
        except Exception as e:
            print(f"[emotion] analysis skipped: {e}")
            emotion_map = {}
    _session_state["emotion_map"] = emotion_map

    progress(0.88, desc=get_text("status_generating_sml"))

    # Build character table for display
    char_table = _build_character_table(characters, voice_assignments, voice_reasons)

    # Build available voices dropdown choices
    char_names = [c.get("normalized_name", "Unknown") for c in characters]
    voice_choices = _build_voice_choices(voice_library)

    progress(0.9, desc=get_text("status_done"))
    gen_status, sml_preview, sml_path = generate_output()
    progress(1.0, desc=get_text("status_done"))

    num_voices = len(voice_assignments)
    status_msg = get_text(
        "success_ready_msg",
        book_id=book_id,
        count=len(characters),
        num_voices=num_voices,
    )
    if emotion_map:
        status_msg += get_text("success_emotions_msg", count=len(emotion_map))

    # Free the local model's VRAM once the book is done; a re-run reloads it.
    unload_model()

    # Update character dropdown choices
    char_dropdown_update = gr.update(choices=char_names, value=char_names[0] if char_names else None)
    first_voice = voice_assignments.get(char_names[0], "") if char_names else ""
    voice_dropdown_update = gr.update(choices=voice_choices, value=first_voice)

    return (
        status_msg,                         # status_output
        char_table,                         # char_table
        gen_status,                         # gen_status
        sml_preview,                        # sml_preview
        sml_path,                           # download
        gr.update(visible=True),            # char_voice_section
        char_dropdown_update,               # char_selector
        voice_dropdown_update,              # voice_selector
        preview_voice(first_voice),
    )


def _build_character_table(characters, voice_assignments, voice_reasons=None):
    """Build a list-of-lists table for the character editor."""
    voice_reasons = voice_reasons or {}
    rows = []
    for char in characters:
        name = char.get("normalized_name", "Unknown")
        gender = char.get("inferred_gender", "unknown")
        age = char.get("inferred_age_category", "unknown")
        voice = voice_assignments.get(name, "")
        voice_display = _voice_display_label(voice) if voice else get_text("none_voice_placeholder")
        rows.append([name, gender, age, voice_display, _character_note(char, voice_reasons.get(name))])
    return rows


def _character_note(char, reason):
    """Short human-readable note explaining a character's voice choice."""
    parts = []
    description = str(char.get("description") or "").strip()
    if description:
        parts.append(description)
    if reason:
        parts.append(str(reason).strip())
    note = " — ".join(part for part in parts if part)
    note = " ".join(note.split())
    return note[:180]


def _build_voice_choices(voice_library):
    """Build dropdown choices as (label, value) for available voices."""
    choices = [(get_text("none_voice_placeholder"), "")]
    all_voices = _get_all_voice_paths(voice_library)
    for v in all_voices:
        choices.append((_voice_display_label(v), v))
    return choices


def on_char_selected(char_name):
    """Called when the user selects a character from the dropdown."""
    voice_assignments = _session_state.get("voice_assignments", {})
    # Pre-select the currently assigned voice in the voice dropdown
    current_voice = voice_assignments.get(char_name, "")
    return gr.update(value=current_voice), preview_voice(current_voice)


def reassign_voice(char_name, voice_path):
    """Assign a voice and immediately update the SML download."""
    if not char_name:
        return gr.update(), gr.update(), gr.update(), gr.update(), None

    if "voice_assignments" not in _session_state:
        _session_state["voice_assignments"] = {}

    if voice_path and voice_path.strip():
        _session_state["voice_assignments"][char_name] = voice_path.strip()
    else:
        _session_state["voice_assignments"].pop(char_name, None)

    char_table = _build_character_table(
        _session_state.get("characters", []),
        _session_state["voice_assignments"],
        _session_state.get("voice_reasons", {}),
    )
    gen_status, sml_preview, sml_path = generate_output()

    return (
        char_table,
        gen_status,
        sml_path,
        sml_preview,
        preview_voice(voice_path),
    )


def generate_output(progress:gr.Progress=gr.Progress())->tuple[str,str,str]:
    """Generate the SML file accepted directly by ebook2audiobook."""
    if "booknlp_data" not in _session_state:
        raise gr.Error(get_text("error_process_first"))

    booknlp_data = _session_state["booknlp_data"]
    characters = _session_state.get("characters", [])
    voice_assignments = _session_state.get("voice_assignments", {})
    book_id = _session_state.get("book_id", "book")
    work_dir = _session_state.get("work_dir", tempfile.mkdtemp(prefix="sml_extractor_"))

    book_txt = booknlp_data.get("book_txt", "")
    has_tokens = bool(booknlp_data.get("tokens"))
    if not book_txt and not has_tokens:
        raise gr.Error(get_text("error_no_book_text"))

    progress(0.3, desc=get_text("status_generating_sml"))

    revision = _session_state.get('generation', 0) + 1
    _session_state['generation'] = revision
    output_dir = os.path.join(work_dir, "sml_output", str(revision))
    os.makedirs(output_dir, exist_ok=True)

    progress(0.5, desc=get_text("status_generating_sml"))

    # Generate path-based SML with voice paths E2A can resolve.
    e2a_sml_path = os.path.join(output_dir, f"{book_id}.e2a.sml.txt")
    portable_assignments = portable_voice_assignments(voice_assignments, _session_state["library_root"])
    generate_sml_output(
        booknlp_data,
        characters,
        e2a_sml_path,
        portable_assignments,
        use_macros=False,
        emotion_map=_session_state.get("emotion_map", {}),
    )

    progress(0.9, desc=get_text("status_done"))

    # Read generated content for preview
    with open(e2a_sml_path, "r", encoding="utf-8") as f:
        sml_content = f.read()

    sml_preview = sml_content[:5000] + ("..." if len(sml_content) > 5000 else "")

    progress(1.0, desc=get_text("status_done"))

    return (
        get_text("sml_generation_ready", book_id=book_id),
        sml_preview,
        e2a_sml_path,
    )


# --- Language switching -------------------------------------------------------

def update_language(lang_code, current_model):
    """Switch the interface language: set the locale and relabel every component.

    Returns one ``gr.update`` per component (module level so tests can call it).
    """
    if lang_code not in ("en", "ru"):
        lang_code = "en"
    set_locale(lang_code)
    table_headers = [
        get_text("char_table_header_character"),
        get_text("char_table_header_gender"),
        get_text("char_table_header_age"),
        get_text("char_table_header_assigned_voice"),
        get_text("char_table_header_notes"),
    ]
    return (
        gr.update(value=f"# {get_text('app_title')}\n{get_text('app_intro')}"),  # header_md
        gr.update(label=get_text("language_selector_label")),                     # lang_accordion
        gr.update(label=get_text("ui_language_label"), info=get_text("switch_language_info")),  # ui_lang
        gr.update(label=get_text("book_language_label")),                          # book_lang
        gr.update(label=get_text("tab_book_download")),                            # tab_book
        gr.update(label=get_text("book_file_label")),                              # input_file
        gr.update(
            label=get_text("key_characters_label"),
            info=get_text("key_characters_info"),
            placeholder=get_text("key_characters_placeholder"),
        ),                                                                        # key_characters
        gr.update(label=get_text("use_llm_label"), info=get_text("use_llm_info")),  # use_llm
        gr.update(
            label=get_text("analyze_emotions_label"),
            info=get_text("analyze_emotions_info"),
        ),                                                                        # use_emotions
        gr.update(
            label=get_text("analysis_model_label"),
            info=get_text("model_info_big") if current_model == "big" else get_text("model_info_small"),
        ),                                                                        # model_size
        gr.update(value=get_text("create_sml_button")),                            # process_btn
        gr.update(label=get_text("status_output_label")),                          # status_output
        gr.update(label=get_text("sml_download_label")),                           # e2a_sml_download
        gr.update(label=get_text("sml_generation_status")),                        # gen_status
        gr.update(label=get_text("preview_script_label")),                         # preview_accordion
        gr.update(label=get_text("sml_preview_label")),                            # sml_preview
        gr.update(label=get_text("tab_characters_voices")),                        # tab_chars
        gr.update(value=get_text("characters_voices_intro")),                      # chars_intro
        gr.update(label=get_text("character_dropdown_label")),                     # char_selector
        gr.update(label=get_text("voice_dropdown_label")),                         # voice_selector
        gr.update(label=get_text("voice_preview_label")),                          # voice_preview
        gr.update(label=get_text("speaking_characters_label")),                    # speaking_accordion
        gr.update(
            headers=table_headers,
            label=get_text("voice_assignments_label"),
        ),                                                                        # char_table
    )


def update_model_info(current_model):
    """Refresh the analysis-model info line after the model choice changes."""
    return gr.update(
        info=get_text("model_info_big") if current_model == "big"
        else get_text("model_info_small")
    )


def create_app() -> gr.Blocks:
    """Create the Gradio web interface with i18n support.

    Two independent language controls:

    * interface language (en/ru) — relabels the whole UI live;
    * book language (eng/rus) — selects the analysis pipeline (English
      BookNLP or the Russian heuristic + BERT coref pipeline) and the voice
      library subfolder scanned for voices.
    """
    locale = get_locale()  # 'en' or 'ru' (E2A_SML_LANG env var)

    with gr.Blocks(title=get_text("app_title")) as app:

        header_md = gr.Markdown(
            f"# {get_text('app_title')}\n{get_text('app_intro')}"
        )

        with gr.Accordion(get_text("language_selector_label"), open=False) as lang_accordion:
            ui_lang = gr.Dropdown(
                choices=[("English", "en"), ("Русский", "ru")],
                value=locale,
                label=get_text("ui_language_label"),
                info=get_text("switch_language_info"),
            )
            book_lang = gr.Dropdown(
                choices=[("English (eng)", "eng"), ("Русский (rus)", "rus")],
                value=os.environ.get("E2A_SML_BOOK_LANG", "eng"),
                label=get_text("book_language_label"),
            )

        with gr.Tab(get_text("tab_book_download")) as tab_book:
            with gr.Row():
                with gr.Column(scale=2):
                    input_file = gr.File(
                        label=get_text("book_file_label"),
                        file_types=[".txt", ".epub", ".mobi", ".pdf", ".html", ".fb2", ".azw", ".azw3"],
                        type="filepath",
                    )
                with gr.Column(scale=1):
                    model_size = gr.Radio(
                        ["small", "big"],
                        value="big",
                        label=get_text("analysis_model_label"),
                        info=get_text("model_info_big"),
                    )

            key_characters = gr.Textbox(
                label=get_text("key_characters_label"),
                placeholder=get_text("key_characters_placeholder"),
                info=get_text("key_characters_info"),
                lines=4,
            )
            use_llm = gr.Checkbox(
                value=True,
                label=get_text("use_llm_label"),
                info=get_text("use_llm_info"),
            )
            use_emotions = gr.Checkbox(
                value=True,
                label=get_text("analyze_emotions_label"),
                info=get_text("analyze_emotions_info"),
            )

            process_btn = gr.Button(get_text("create_sml_button"), variant="primary")
            status_output = gr.Textbox(label=get_text("status_output_label"), interactive=False)
            e2a_sml_download = gr.File(label=get_text("sml_download_label"), interactive=False)
            gen_status = gr.Textbox(label=get_text("sml_generation_status"), interactive=False)
            with gr.Accordion(get_text("preview_script_label"), open=False) as preview_accordion:
                sml_preview = gr.Textbox(label=get_text("sml_preview_label"), lines=10, interactive=False)

        with gr.Tab(get_text("tab_characters_voices")) as tab_chars:
            chars_intro = gr.Markdown(get_text("characters_voices_intro"))

            with gr.Group(visible=False) as char_voice_section:
                with gr.Row():
                    char_selector = gr.Dropdown(
                        label=get_text("character_dropdown_label"),
                        choices=[],
                        interactive=True,
                    )
                    voice_selector = gr.Dropdown(
                        label=get_text("voice_dropdown_label"),
                        choices=[],
                        interactive=True,
                    )
                voice_preview = gr.Audio(label=get_text("voice_preview_label"), interactive=False)

            with gr.Accordion(get_text("speaking_characters_label"), open=False) as speaking_accordion:
                char_table = gr.Dataframe(
                    headers=[
                        get_text("char_table_header_character"),
                        get_text("char_table_header_gender"),
                        get_text("char_table_header_age"),
                        get_text("char_table_header_assigned_voice"),
                        get_text("char_table_header_notes"),
                    ],
                    datatype=["str", "str", "str", "str", "str"],
                    label=get_text("voice_assignments_label"),
                    interactive=False,
                )

        # --- Language switching -------------------------------------------------
        ui_lang.change(
            fn=update_language,
            inputs=[ui_lang, model_size],
            outputs=[
                header_md, lang_accordion, ui_lang, book_lang, tab_book,
                input_file, key_characters, use_llm, use_emotions, model_size, process_btn,
                status_output, e2a_sml_download, gen_status, preview_accordion,
                sml_preview, tab_chars, chars_intro, char_selector, voice_selector,
                voice_preview, speaking_accordion, char_table,
            ],
        )

        model_size.change(
            fn=update_model_info,
            inputs=[model_size],
            outputs=[model_size],
        )

        # Process book → populate character table, dropdowns, and preview
        process_btn.click(
            fn=process_book,
            inputs=[input_file, model_size, book_lang, key_characters, use_llm, use_emotions],
            outputs=[
                status_output,
                char_table,
                gen_status,
                sml_preview,
                e2a_sml_download,
                char_voice_section,
                char_selector,
                voice_selector,
                voice_preview,
            ],
        )

        # Selecting a character → show details and current voice
        char_selector.change(
            fn=on_char_selected,
            inputs=[char_selector],
            outputs=[voice_selector, voice_preview],
        )

        # Only user changes trigger regeneration; selecting another character
        # updates the dropdown without changing its assigned voice.
        voice_selector.input(
            fn=reassign_voice,
            inputs=[char_selector, voice_selector],
            outputs=[char_table, gen_status, e2a_sml_download, sml_preview, voice_preview],
        )

    return app


if __name__ == "__main__":
    # Set the interface language before the app is built so every label
    # renders in the requested locale from the start.
    if os.environ.get("E2A_SML_LANG"):
        set_locale(os.environ["E2A_SML_LANG"])
    app = create_app()
    app.launch(server_name="127.0.0.1", server_port=7861, theme=gr.themes.Soft(), css=APP_CSS)
