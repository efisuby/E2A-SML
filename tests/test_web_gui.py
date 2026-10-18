import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import web_gui
from sml_extractor.character_input import parse_key_characters


class GuiFlowTests(unittest.TestCase):
    def test_analysis_generates_sml_and_voice_change_regenerates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            voices = []
            for name in ('one', 'two'):
                path = root / 'voices' / 'eng' / 'adult' / 'female' / f'{name}.wav'
                path.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(path), 'wb') as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(8000)
                    audio.writeframes(b'\0' * 160)
                voices.append(path)

            data = {
                'tokens': [
                    {'token_ID_within_document': str(i), 'paragraph_ID': '0', 'word': word}
                    for i, word in enumerate(['“', 'Hello', '”', 'he', 'said', '.'])
                ],
                'quotes': [{'quote_start': '0', 'quote_end': '2', 'char_id': '1'}],
                'book_data': {'characters': [
                    {'id': 1, 'mentions': {'proper': [{'n': 'Jeremiah'}]}}
                ]},
            }
            chars = [
                {'normalized_name': 'Narrator', 'inferred_gender': 'unknown'},
                {'normalized_name': 'Jeremiah', 'inferred_gender': 'male'},
            ]
            library = {'adult': {'female': [str(path) for path in voices], 'male': []}}
            web_gui._session_state.clear()
            with (
                patch.object(web_gui, 'configured_library_root', return_value=root),
                patch.object(web_gui, 'ensure_voice_library'),
                patch.object(web_gui, 'convert_ebook_to_txt', return_value='book.txt'),
                patch.object(web_gui, 'check_booknlp_installation', return_value=(True, 'ok')) as check_mock,
                patch.object(web_gui, 'run_booknlp', return_value={'book_id': 'book'}) as run_mock,
                patch.object(web_gui, 'load_booknlp_output', return_value=data),
                patch.object(web_gui, 'extract_characters', return_value=chars),
                patch.object(web_gui, 'scan_voice_library', return_value=library) as scan_mock,
                patch.object(web_gui, 'llm_available', return_value=False),
            ):
                result = web_gui.process_book('book.epub', 'big', 'eng')

            # The selected book language reaches every language-aware step.
            check_mock.assert_called_once_with('eng')
            run_args = run_mock.call_args
            self.assertEqual(run_args.args[0], 'book.txt')
            self.assertEqual(run_args.args[2:], ('big', 'eng'))
            self.assertEqual(scan_mock.call_args.args[1], 'eng')

            self.assertEqual(len(result), 9)
            initial_file = Path(result[4])
            self.assertTrue(initial_file.is_file())
            self.assertIn('Hello', initial_file.read_text())
            self.assertEqual(result[8], web_gui.preview_voice(result[7]['value']))
            self.assertEqual(
                web_gui.preview_voice('voices/eng/adult/female/one.wav'),
                str(voices[0].resolve()),
            )

            new_voice = str(voices[0])
            if web_gui._session_state['voice_assignments']['Jeremiah'] == new_voice:
                new_voice = str(voices[1])
            changed = web_gui.reassign_voice('Jeremiah', new_voice)
            self.assertEqual(len(changed), 5)
            regenerated = changed[2]
            self.assertNotEqual(initial_file, Path(regenerated))
            self.assertIn(f'[voice:voices/eng/adult/female/{Path(new_voice).name}]', Path(regenerated).read_text())


class LanguageSwitchTests(unittest.TestCase):
    """The interface-language dropdown relabels every component in place."""

    def setUp(self):
        import os
        self._previous_lang = os.environ.get('E2A_SML_LANG')
        self.addCleanup(self._restore_locale)

    def _restore_locale(self):
        import os
        if self._previous_lang is None:
            os.environ.pop('E2A_SML_LANG', None)
        else:
            os.environ['E2A_SML_LANG'] = self._previous_lang

    def test_switch_to_russian_relabels_all_components(self):
        from i18n import TRANSLATIONS, get_locale

        updates = web_gui.update_language('ru', 'big')

        updates = web_gui.update_language('ru', 'big')

        # One gr.update per wired component (create_app's outputs list).
        self.assertEqual(len(updates), 23)
        self.assertTrue(all(u.get('__type__') == 'update' for u in updates))

        self.assertEqual(get_locale(), 'ru')
        ru = TRANSLATIONS['ru']
        self.assertEqual(updates[11]['label'], ru['status_output_label'])   # status_output
        self.assertEqual(updates[10]['value'], ru['create_sml_button'])     # process button
        self.assertEqual(updates[6]['label'], ru['key_characters_label'])   # key characters
        self.assertEqual(updates[7]['label'], ru['use_llm_label'])          # LLM checkbox
        self.assertEqual(updates[8]['label'], ru['analyze_emotions_label'])  # emotion checkbox
        self.assertEqual(updates[22]['headers'][0], ru['char_table_header_character'])
        self.assertEqual(
            updates[22]['headers'][4], ru['char_table_header_notes']
        )
        self.assertIn(ru['app_intro'], updates[0]['value'])                 # header markdown

        # Switching back restores English labels.
        updates = web_gui.update_language('en', 'small')
        en = TRANSLATIONS['en']
        self.assertEqual(get_locale(), 'en')
        self.assertEqual(updates[11]['label'], en['status_output_label'])
        self.assertEqual(updates[9]['info'], en['model_info_small'])        # model radio info

    def test_unknown_language_falls_back_to_english(self):
        from i18n import get_locale

        web_gui.update_language('de', 'big')
        self.assertEqual(get_locale(), 'en')

    def test_create_app_builds_with_current_locale(self):
        import gradio as gr

        app = web_gui.create_app()
        self.assertIsInstance(app, gr.Blocks)


class KeyCharacterTests(unittest.TestCase):
    """The explicit key-character list reaches the table and the casting."""

    KEY_TEXT = (
        'Гарвель Локен — капитан 10-й роты, главный герой\n'
        'Севатар — первый капитан'
    )

    def _process(self, key_text, use_llm, emotion_fn=None):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('narrator', 'loken'):
                path = root / 'voices' / 'rus' / 'adult' / 'female' / f'{name}.wav'
                path.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(path), 'wb') as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(8000)
                    audio.writeframes(b'\0' * 160)

            data = {
                'tokens': [
                    {'token_ID_within_document': str(i), 'paragraph_ID': '0', 'word': word}
                    for i, word in enumerate(['«', 'Привет', '»', '—', 'сказал', 'он', '.'])
                ],
                'quotes': [{'quote_start': '0', 'quote_end': '2', 'char_id': '1'}],
                'book_data': {'characters': [
                    {'id': 1, 'mentions': {'proper': [{'n': 'Локен'}]}}
                ]},
            }
            chars = [
                {'normalized_name': 'Narrator', 'inferred_gender': 'unknown'},
                {'normalized_name': 'Локен', 'inferred_gender': 'male'},
            ]
            library = {'adult': {'female': [
                'voices/rus/adult/female/ALEKSANDRA_KOSTINSKAYa.mp3',
            ], 'male': ['voices/rus/adult/male/AbdulovV.mp3']}}
            web_gui._session_state.clear()
            with (
                patch.object(web_gui, 'configured_library_root', return_value=root),
                patch.object(web_gui, 'ensure_voice_library'),
                patch.object(web_gui, 'convert_ebook_to_txt', return_value='book.txt'),
                patch.object(web_gui, 'check_booknlp_installation', return_value=(True, 'ok')),
                patch.object(web_gui, 'run_booknlp', return_value={'book_id': 'book'}),
                patch.object(web_gui, 'load_booknlp_output', return_value=data),
                patch.object(web_gui, 'extract_characters', return_value=chars),
                patch.object(web_gui, 'scan_voice_library', return_value=library),
                patch.object(web_gui, 'llm_available', return_value=use_llm),
                # Emotion labelling is a best-effort extra: keep it offline.
                patch.object(
                    web_gui, 'analyze_book_emotions',
                    side_effect=emotion_fn or (lambda segments, **kwargs: {}),
                ),
                # Keep the offline parser so the tests never touch a live LLM.
                patch.object(
                    web_gui, 'parse_key_characters',
                    side_effect=lambda text, use_llm=True: parse_key_characters(
                        text, use_llm=False
                    ),
                ),
            ):
                return web_gui.process_book(
                    'book.fb2', 'small', 'rus', key_text, use_llm
                )

    def test_key_characters_are_merged_and_cast(self):
        table = self._process(self.KEY_TEXT, use_llm=False)[1]
        names = [row[0] for row in table]
        self.assertIn('Локен', names)
        self.assertIn('Севатар', names)  # missed by BookNLP, added from the list

        loken = next(row for row in table if row[0] == 'Локен')
        self.assertIn('капитан 10-й роты', loken[4])  # description surfaced
        self.assertNotEqual(loken[3], '(нет)')        # and it got a voice
        self.assertEqual(loken[1], 'male')

    def test_llm_casting_is_used_when_available(self):
        with patch.object(
            web_gui, 'assign_voices_with_llm',
            return_value=(
                {'Локен': 'voices/rus/adult/male/AbdulovV.mp3'},
                {'Локен': 'низкий мужской голос'},
            ),
        ) as cast_mock:
            table = self._process(self.KEY_TEXT, use_llm=True)[1]

        cast_mock.assert_called_once()
        loken = next(row for row in table if row[0] == 'Локен')
        self.assertIn('AbdulovV', loken[3])
        self.assertIn('низкий мужской голос', loken[4])

    def test_llm_failure_falls_back_to_auto_assign(self):
        with patch.object(
            web_gui, 'assign_voices_with_llm', side_effect=RuntimeError('boom')
        ):
            table = self._process(self.KEY_TEXT, use_llm=True)[1]

        loken = next(row for row in table if row[0] == 'Локен')
        self.assertNotEqual(loken[3], '(нет)')

    def test_emotions_are_tagged_in_sml(self):
        result = self._process(
            self.KEY_TEXT,
            use_llm=True,
            emotion_fn=lambda segments, **kwargs: {
                text: 'happy' for speaker, text in segments if speaker == 'Локен'
            },
        )

        sml = Path(result[4]).read_text()
        self.assertIn('[emotion:happy]', sml)
        self.assertIn('[/emotion]', sml)

    def test_emotion_analysis_failure_keeps_untagged_sml(self):
        def boom(segments, **kwargs):
            raise RuntimeError('no model')

        result = self._process(self.KEY_TEXT, use_llm=True, emotion_fn=boom)

        sml = Path(result[4]).read_text()
        self.assertNotIn('[emotion:', sml)
        self.assertIn('[voice:', sml)


if __name__ == '__main__':
    unittest.main()
