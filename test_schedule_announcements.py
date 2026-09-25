# -*- coding: utf-8 -*-
"""Offline tests for the data-driven schedule parser."""

import unittest
import os
import json
import hashlib
import tempfile
from datetime import date, datetime
from unittest.mock import patch, Mock, call

import schedule_announcements as schedule_data


class ScheduleParserTests(unittest.TestCase):
    def setUp(self):
        self.subject_rows = [
            ["Предмет", "Скорочення", "Посилання", "Викладач"],
            ["Комерційна діяльність та технологія торгівлі", "КД", "https://example.test/zoom", "Непочатова Г.В."],
            ["Облік, оподаткування та страхування в комерційній діяльності", "ООСвКД", "https://example.test/accounting", "Попова І.А."],
        ]
        self.directory = schedule_data.parse_subjects(self.subject_rows)

    def test_window_words_include_free_replacement(self):
        self.assertTrue(schedule_data.is_window("ВІЛЬНА"))
        self.assertEqual(schedule_data.resolve_subject("ВІЛЬНА", self.directory)["subject"], "Вікно")
        self.assertTrue(schedule_data.resolve_subject("---", self.directory)["window"])

    def test_alias_can_be_embedded_in_replacement_text(self):
        item = schedule_data.resolve_subject("КД (ауд. 201)", self.directory)
        self.assertTrue(item["known"])
        self.assertEqual(item["subject"], "Комерційна діяльність та технологія торгівлі")

    def test_partial_title_takes_priority_over_another_subjects_short_alias(self):
        for raw in (
            "Облік, оподаткування та страхування в КД",
            "облік оподаткування та страхування в кд",
            "Облік, оподаткування та страхування в К.Д.",
        ):
            with self.subTest(raw=raw):
                item = schedule_data.resolve_subject(raw, self.directory)
                self.assertTrue(item["known"])
                self.assertEqual(item["subject"], "Облік, оподаткування та страхування в комерційній діяльності")
                self.assertEqual(item["url"], "https://example.test/accounting")

    def test_partial_title_expansion_uses_subjects_from_the_directory(self):
        directory = schedule_data.parse_subjects([
            ["Предмет", "Скорочення", "Посилання", "Викладач"],
            ["Технологія і організація готельного господарства", "ТОГГ", "https://example.test/hotel", "Викладач"],
        ])
        item = schedule_data.resolve_subject("Технологія і організація ГГ", directory)
        self.assertTrue(item["known"])
        self.assertEqual(item["subject"], "Технологія і організація готельного господарства")
        self.assertEqual(item["url"], "https://example.test/hotel")

    def test_ambiguous_partial_title_does_not_fall_back_to_short_alias(self):
        directory = schedule_data.parse_subjects(self.subject_rows + [
            ["Облік, оподаткування та страхування в кредитній діяльності", "ООСвКрД", "https://example.test/credit", "Інший викладач"],
        ])
        raw = "Облік, оподаткування та страхування в КД"
        item = schedule_data.resolve_subject(raw, directory)
        self.assertFalse(item["known"])
        self.assertEqual(item["subject"], raw)
        self.assertEqual(item["url"], "")

    def test_unknown_title_cannot_be_resolved_by_an_alias_inside_it(self):
        raw = "Нова дисципліна в КД"
        item = schedule_data.resolve_subject(raw, self.directory)
        self.assertFalse(item["known"])
        self.assertEqual(item["subject"], raw)
        self.assertEqual(item["url"], "")

    def test_group_matching_is_boundary_aware(self):
        self.assertTrue(schedule_data.group_matches("Т-32", "T-32"))
        self.assertTrue(schedule_data.group_matches("Т32", "Т-32"))
        self.assertFalse(schedule_data.group_matches("ПТ-32", "Т-32"))
        self.assertFalse(schedule_data.group_matches("Т-321", "Т-32"))

    def test_replacements_reset_after_another_group(self):
        rows = [
            ["Розпорядження про заміну на 07.09.2026 під рискою"],
            ["", "Т-32", "1", "ВІЛЬНА", "", "", ""],
            ["", "", "2", "КД", "", "Іваненко І.І.", ""],
            ["", "ПТ-32", "3", "КД", "", "Чужий В.В.", ""],
            ["", "", "4", "ВІЛЬНА", "", "", ""],
        ]
        replacements, info = schedule_data.parse_replacements(rows, date(2026, 9, 7), "T-32")
        self.assertEqual(sorted(replacements), [1, 2])
        self.assertEqual(replacements[1]["raw_subject"], "ВІЛЬНА")
        self.assertEqual(info["duplicates"], [])

    def test_replacement_duplicates_are_reported(self):
        rows = [
            ["на 07.09.2026"],
            ["", "Т-32", "1", "ВІЛЬНА"],
            ["", "Т-32", "1", "КД"],
        ]
        replacements, info = schedule_data.parse_replacements(rows, date(2026, 9, 7), "Т-32")
        self.assertEqual(replacements[1]["raw_subject"], "КД")
        self.assertEqual(info["duplicates"], [1])

    def test_week_ranges_and_two_row_schedule(self):
        semester = schedule_data.parse_semester([
            ["НАД РИСКОЮ", "ПІД РИСКОЮ"],
            ["31.08.2026-06.09.2026", "07.09.2026-13.09.2026"],
        ])
        self.assertEqual(schedule_data.week_kind_for(date(2026, 9, 1), semester), "above")
        self.assertEqual(schedule_data.week_kind_for(date(2026, 9, 7), semester), "below")

        base = schedule_data.parse_base_schedule([
            ["", "Понеділок", "Вівторок", "Середа"],
            ["8:30-9:50", "КД", "", "---"],
            ["", "", "ООСвКД", ""],
        ])
        self.assertEqual(base["slots"][0]["upper"]["понеділок"], "КД")
        self.assertEqual(base["slots"][0]["lower"]["вівторок"], "ООСвКД")

    def test_build_announcement_overlays_free_replacement(self):
        base_rows = [
            ["", "Понеділок", "Вівторок"],
            ["8:30-9:50", "КД", ""],
            ["", "КД", ""],
        ]
        semester_rows = [
            ["НАД РИСКОЮ", "ПІД РИСКОЮ"],
            ["31.08.2026-06.09.2026", "07.09.2026-13.09.2026"],
        ]
        replacement_rows = [
            ["на 07.09.2026"],
            ["", "Т-32", "1", "ВІЛЬНА", "", "НАД РИСКОЮ"],
        ]
        config = {
            "BASE_SCHEDULE_CSV_URL": "base",
            "SUBJECTS_CSV_URL": "subjects",
            "SEMESTER_CSV_URL": "semester",
            "REPLACEMENTS_CSV_URL": "replacements",
            "SCHEDULE_GROUP": "T-32",
        }
        with patch.dict(os.environ, config, clear=False), patch.object(
            schedule_data,
            "fetch_with_cache",
            side_effect=[
                (base_rows, False),
                (self.subject_rows, False),
                (semester_rows, False),
                (replacement_rows, False),
            ],
        ):
            message, diagnostics = schedule_data.build_daily_announcement(date(2026, 9, 7))
        self.assertIn("🪟 Вікно", message)
        self.assertIn("🔄", message)
        self.assertNotIn("НАД РИСКОЮ", message)
        self.assertFalse(diagnostics["replacement_info"]["ignored"])

    def test_morning_announcement_uses_accounting_link_for_partial_title(self):
        sources = {
            "base": [["", "П'ятниця", "Четвер"], ["8:30-9:50", "---", ""], ["", "", ""]],
            "subjects": self.subject_rows,
            "semester": [["НАД РИСКОЮ", "ПІД РИСКОЮ"], ["14.09.2026-20.09.2026", "21.09.2026-27.09.2026"]],
            "replacements": [
                ["Розпорядження про заміну занять на П'ЯТНИЦЮ 25.09.2026 ПІД рискою"],
                ["", "Т - 32", "1", "Облік, оподаткування та страхування в КД", "", "Попова І.А.", "", "Розклад дзвінків", "", ""],
            ],
        }
        config = {
            "BASE_SCHEDULE_CSV_URL": "base",
            "SUBJECTS_CSV_URL": "subjects",
            "SEMESTER_CSV_URL": "semester",
            "REPLACEMENTS_CSV_URL": "replacements",
            "SCHEDULE_GROUP": "T-32",
        }
        with patch.dict(os.environ, config), patch.object(
            schedule_data, "fetch_with_cache", side_effect=lambda url, key: (sources[key], False),
        ):
            message, diagnostics = schedule_data.build_daily_announcement(date(2026, 9, 25))
        self.assertIn("8:30–9:50", message)
        self.assertIn("🔄 Облік, оподаткування та страхування в комерційній діяльності", message)
        self.assertIn('href="https://example.test/accounting"', message)
        self.assertNotIn('href="https://example.test/zoom"', message)
        self.assertIn("Попова І.А.", message)
        self.assertEqual(diagnostics["unknown_subjects"], [])


class GeminiSubjectMatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_path = os.path.join(self.temp_dir.name, "gemini-cache.json")
        self.env_patcher = patch.dict(os.environ, {"GEMINI_MATCH_CACHE_FILE": self.cache_path}, clear=False)
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        self.directory = schedule_data.parse_subjects([
            ["Предмет", "Скорочення", "Посилання", "Викладач"],
            ["Комерційна діяльність та технологія торгівлі", "КД", "https://example.test/commerce", "Непочатова Г.В."],
            ["Облік, оподаткування та страхування в комерційній діяльності", "ООСвКД", "https://example.test/accounting", "Попова І.А."],
        ])

    @staticmethod
    def _response(matches):
        response = Mock()
        response.json.return_value = {
            "candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [{"text": json.dumps({"matches": matches})}]},
            }],
        }
        return response

    def test_gemini_selects_a_subject_from_the_live_directory(self):
        raw = "Облік, оподаткування та страхування в КД"
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", return_value=self._response([
                {"query_id": "Q000", "subject_id": "S001"},
            ]),
        ) as post:
            matches = schedule_data.match_unknown_subjects([raw], self.directory)

        self.assertEqual(matches[schedule_data.normalized(raw)]["subject"], "Облік, оподаткування та страхування в комерційній діяльності")
        self.assertEqual(matches[schedule_data.normalized(raw)]["url"], "https://example.test/accounting")
        request = post.call_args
        self.assertEqual(request.kwargs["headers"]["x-goog-api-key"], "test-key")
        body = json.dumps(request.kwargs["json"], ensure_ascii=False)
        self.assertIn(raw, body)
        self.assertIn("Облік, оподаткування та страхування в комерційній діяльності", body)
        self.assertNotIn("https://example.test", body)
        self.assertNotIn("Попова", body)

    def test_gemini_retries_an_unresolved_subject_after_one_minute(self):
        raw = "Облік та страхування у КД"
        no_match = self._response([{"query_id": "Q000", "subject_id": "NONE"}])
        match = self._response([{"query_id": "Q000", "subject_id": "S001"}])
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", side_effect=[no_match, match],
        ) as post, patch("time.sleep") as sleep:
            matches = schedule_data.match_unknown_subjects([raw], self.directory)

        self.assertEqual(
            matches.get(schedule_data.normalized(raw), {}).get("subject"),
            "Облік, оподаткування та страхування в комерційній діяльності",
        )
        self.assertEqual(post.call_count, 2)
        self.assertEqual(sleep.call_args_list, [call(60)])

    def test_gemini_uses_a_match_from_the_third_attempt(self):
        raw = "Облік та страхування у КД"
        no_match = self._response([{"query_id": "Q000", "subject_id": "NONE"}])
        match = self._response([{"query_id": "Q000", "subject_id": "S001"}])
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", side_effect=[no_match, no_match, match],
        ) as post, patch("time.sleep") as sleep:
            matches = schedule_data.match_unknown_subjects([raw], self.directory)

        self.assertEqual(
            matches.get(schedule_data.normalized(raw), {}).get("subject"),
            "Облік, оподаткування та страхування в комерційній діяльності",
        )
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(60), call(60)])

    def test_gemini_retries_only_unresolved_labels(self):
        raw_subjects = ["Облік та страхування у КД", "КД та торгівля"]
        partial = self._response([
            {"query_id": "Q000", "subject_id": "S001"},
            {"query_id": "Q001", "subject_id": "NONE"},
        ])
        remaining = self._response([{"query_id": "Q001", "subject_id": "S000"}])
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", side_effect=[partial, remaining],
        ) as post, patch("time.sleep") as sleep:
            matches = schedule_data.match_unknown_subjects(raw_subjects, self.directory)

        self.assertEqual(
            matches.get(schedule_data.normalized(raw_subjects[0]), {}).get("subject"),
            "Облік, оподаткування та страхування в комерційній діяльності",
        )
        self.assertEqual(
            matches.get(schedule_data.normalized(raw_subjects[1]), {}).get("subject"),
            "Комерційна діяльність та технологія торгівлі",
        )
        self.assertEqual(post.call_count, 2)
        first_prompt = post.call_args_list[0].kwargs["json"]["contents"][0]["parts"][0]["text"]
        second_prompt = post.call_args_list[1].kwargs["json"]["contents"][0]["parts"][0]["text"]
        self.assertIn(raw_subjects[0], first_prompt)
        self.assertIn(raw_subjects[1], first_prompt)
        self.assertNotIn(raw_subjects[0], second_prompt)
        self.assertIn(raw_subjects[1], second_prompt)
        self.assertEqual(sleep.call_args_list, [call(60)])

    def test_gemini_falls_back_and_caches_only_after_three_failed_attempts(self):
        raw = "Незрозумілий предмет"
        no_match = self._response([{"query_id": "Q000", "subject_id": "NONE"}])
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", return_value=no_match,
        ) as post, patch("time.sleep") as sleep:
            first = schedule_data.match_unknown_subjects([raw], self.directory)
            second = schedule_data.match_unknown_subjects([raw], self.directory)

        self.assertEqual(first, {})
        self.assertEqual(second, {})
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(60), call(60)])

    def test_gemini_retries_legacy_cached_negative_result(self):
        raw = "Незрозумілий предмет"
        fingerprint = hashlib.sha256(json.dumps({
            "model": schedule_data.GEMINI_MODEL,
            "subjects": [
                [schedule_data.normalized(entry["subject"]), schedule_data.normalized(entry.get("alias", ""))]
                for entry in self.directory["entries"]
            ],
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
        with open(self.cache_path, "w", encoding="utf-8") as cache_file:
            json.dump({
                "catalog_fingerprint": fingerprint,
                "matches": {schedule_data.normalized(raw): None},
            }, cache_file)

        no_match = self._response([{"query_id": "Q000", "subject_id": "NONE"}])
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", return_value=no_match,
        ) as post, patch("time.sleep") as sleep:
            result = schedule_data.match_unknown_subjects([raw], self.directory)

        self.assertEqual(result, {})
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(60), call(60)])

    def test_gemini_none_leaves_the_subject_unmatched(self):
        raw = "Незрозумілий предмет"
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", return_value=self._response([
                {"query_id": "Q000", "subject_id": "NONE"},
            ]),
        ) as post, patch("time.sleep") as sleep:
            matches = schedule_data.match_unknown_subjects([raw], self.directory)
        self.assertEqual(matches, {})
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(60), call(60)])

    def test_gemini_cannot_return_a_subject_outside_the_directory(self):
        raw = "Невідома назва"
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", return_value=self._response([
                {"query_id": "Q000", "subject_id": "invented-subject"},
            ]),
        ) as post, patch("time.sleep") as sleep:
            matches = schedule_data.match_unknown_subjects([raw], self.directory)
        self.assertEqual(matches, {})
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(60), call(60)])

    def test_gemini_resolves_multiple_unknown_labels_in_one_request(self):
        raw_subjects = ["Облік та страхування у КД", "КД та торгівля"]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", return_value=self._response([
                {"query_id": "Q000", "subject_id": "S001"},
                {"query_id": "Q001", "subject_id": "S000"},
            ]),
        ) as post:
            matches = schedule_data.match_unknown_subjects(raw_subjects, self.directory)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(matches[schedule_data.normalized(raw_subjects[0])]["subject"], "Облік, оподаткування та страхування в комерційній діяльності")
        self.assertEqual(matches[schedule_data.normalized(raw_subjects[1])]["subject"], "Комерційна діяльність та технологія торгівлі")

    def test_gemini_reuses_mapping_and_reads_current_directory_link(self):
        raw = "Облік та страхування у КД"
        rows = [
            ["Предмет", "Скорочення", "Посилання", "Викладач"],
            ["Комерційна діяльність та технологія торгівлі", "КД", "https://example.test/commerce", "Непочатова Г.В."],
            ["Облік, оподаткування та страхування в комерційній діяльності", "ООСвКД", "https://example.test/accounting", "Попова І.А."],
        ]
        updated_rows = [row[:] for row in rows]
        updated_rows[2][2] = "https://example.test/accounting-updated"
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "gemini-cache.json")
            environment = {"GEMINI_API_KEY": "test-key", "GEMINI_MATCH_CACHE_FILE": cache_path}
            with patch.dict(os.environ, environment, clear=False), patch.object(
                schedule_data.requests, "post", return_value=self._response([
                    {"query_id": "Q000", "subject_id": "S001"},
                ]),
            ) as post:
                first = schedule_data.match_unknown_subjects([raw], schedule_data.parse_subjects(rows))
                second = schedule_data.match_unknown_subjects([raw], schedule_data.parse_subjects(updated_rows))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(first[schedule_data.normalized(raw)]["url"], "https://example.test/accounting")
        self.assertEqual(second[schedule_data.normalized(raw)]["url"], "https://example.test/accounting-updated")

    def test_gemini_cache_is_invalidated_when_the_subject_catalog_changes(self):
        raw = "Облік та страхування у КД"
        rows = [
            ["Предмет", "Скорочення", "Посилання", "Викладач"],
            ["Комерційна діяльність та технологія торгівлі", "КД", "https://example.test/commerce", "Непочатова Г.В."],
            ["Облік, оподаткування та страхування в комерційній діяльності", "ООСвКД", "https://example.test/accounting", "Попова І.А."],
        ]
        changed_rows = [row[:] for row in rows]
        changed_rows[2][0] = "Облік і страхування в комерційній діяльності"
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", side_effect=[
                self._response([{"query_id": "Q000", "subject_id": "S001"}]),
                self._response([{"query_id": "Q000", "subject_id": "S001"}]),
            ],
        ) as post:
            schedule_data.match_unknown_subjects([raw], schedule_data.parse_subjects(rows))
            updated = schedule_data.match_unknown_subjects([raw], schedule_data.parse_subjects(changed_rows))
        self.assertEqual(post.call_count, 2)
        self.assertEqual(updated[schedule_data.normalized(raw)]["subject"], "Облік і страхування в комерційній діяльності")

    def test_gemini_caches_unmatched_result_for_unchanged_catalog(self):
        raw = "Незрозумілий предмет"
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", return_value=self._response([
                {"query_id": "Q000", "subject_id": "NONE"},
            ]),
        ) as post, patch("time.sleep") as sleep:
            first = schedule_data.match_unknown_subjects([raw], self.directory)
            second = schedule_data.match_unknown_subjects([raw], self.directory)
        self.assertEqual(first, {})
        self.assertEqual(second, {})
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(60), call(60)])

    def test_malformed_gemini_response_is_ignored(self):
        response = Mock()
        response.json.return_value = []
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", return_value=response,
        ) as post, patch("time.sleep") as sleep, self.assertLogs(schedule_data.__name__, level="WARNING"):
            matches = schedule_data.match_unknown_subjects(["Невідома назва"], self.directory)
        self.assertEqual(matches, {})
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(60), call(60)])

    def test_gemini_is_skipped_when_api_key_is_not_configured(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(schedule_data.requests, "post") as post:
            matches = schedule_data.match_unknown_subjects(["Новий предмет"], self.directory)
        self.assertEqual(matches, {})
        post.assert_not_called()

    def test_api_failure_leaves_subject_unmatched_without_raising(self):
        raw = "Невідома назва"
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data.requests, "post", side_effect=schedule_data.requests.Timeout,
        ) as post, patch("time.sleep") as sleep, self.assertLogs(schedule_data.__name__, level="WARNING"):
            matches = schedule_data.match_unknown_subjects([raw], self.directory)
        self.assertEqual(matches, {})
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(60), call(60)])

    def test_morning_announcement_uses_gemini_match_and_official_link(self):
        raw = "Облік та страхування у КД"
        sources = {
            "base": [["", "Понеділок", "Вівторок"], ["8:30-9:50", "---", "---"], ["", "", ""]],
            "subjects": self.directory["entries"],
            "semester": [["НАД РИСКОЮ", "ПІД РИСКОЮ"], ["31.08.2026-06.09.2026", "07.09.2026-13.09.2026"]],
            "replacements": [["на 07.09.2026"], ["", "Т-32", "1", raw, "", "Заміна В.В."]],
        }
        sources["subjects"] = [
            ["Предмет", "Скорочення", "Посилання", "Викладач"],
            *[[entry["subject"], entry["alias"], entry["url"], entry["teacher"]] for entry in self.directory["entries"]],
        ]
        config = {
            "BASE_SCHEDULE_CSV_URL": "base",
            "SUBJECTS_CSV_URL": "subjects",
            "SEMESTER_CSV_URL": "semester",
            "REPLACEMENTS_CSV_URL": "replacements",
            "SCHEDULE_GROUP": "T-32",
        }
        with patch.dict(os.environ, config, clear=False), patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False), patch.object(
            schedule_data, "fetch_with_cache", side_effect=lambda url, key: (sources[key], False),
        ), patch.object(
            schedule_data.requests, "post", return_value=self._response([
                {"query_id": "Q000", "subject_id": "S001"},
            ]),
        ):
            message, diagnostics = schedule_data.build_daily_announcement(date(2026, 9, 7))

        self.assertIn("🔄 Облік, оподаткування та страхування в комерційній діяльності", message)
        self.assertIn('href="https://example.test/accounting"', message)
        self.assertNotIn('href="https://example.test/commerce"', message)
        self.assertIn("Заміна В.В.", message)
        self.assertIn("Gemini", message)
        self.assertEqual(diagnostics["unknown_subjects"], [])
        self.assertEqual(diagnostics["ai_matches"], [{
            "raw": raw,
            "subject": "Облік, оподаткування та страхування в комерційній діяльності",
        }])


class TelegramSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot
        cls.bot = bot

    def test_send_message_uses_one_target(self):
        bot = self.bot
        bot.TELEGRAM_TOKEN = "test-token"
        bot.CHANNEL_ID = "-100-group"

        class Response:
            ok = True

            @staticmethod
            def json():
                return {"ok": True}

        with patch.object(bot.requests, "post", return_value=Response()) as post:
            self.assertTrue(bot.send_message("test"))
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["chat_id"], "-100-group")

    def test_private_target_rejects_group_id(self):
        with patch.dict(self.bot.os.environ, {"PRIVATE_TEST_CHAT_ID": "-100123"}, clear=False):
            with self.assertRaises(RuntimeError):
                self.bot._resolve_private_test_target()

    def test_private_test_does_not_mark_group_state(self):
        bot = self.bot
        with patch.object(bot, "build_daily_announcement", return_value=("message", {})) as build, patch.object(bot, "send_message", return_value=True) as send, patch.object(bot, "load_state", return_value={}) as load, patch.object(bot, "save_state") as save_state:
            self.assertTrue(
                bot.check_schedule(
                    force=True,
                    target_chat_id="123456",
                    target_day=date(2026, 9, 7),
                )
            )
        save_state.assert_not_called()

    def test_normal_schedule_skips_already_marked_day(self):
        bot = self.bot
        with patch.object(
            bot,
            "load_state",
            return_value={"last_schedule_announcement": "2026-09-07"},
        ), patch.object(bot, "build_daily_announcement") as build:
            self.assertFalse(
                bot.check_schedule(
                    force=False,
                    target_day=date(2026, 9, 7),
                )
            )
        build.assert_not_called()

    def test_schedule_target_skips_weekend(self):
        self.assertEqual(
            self.bot._next_school_day(date(2026, 9, 4)),
            date(2026, 9, 7),
        )



class SchedulerSplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot
        cls.bot = bot

    def test_weekday_morning_runs_announcement_and_birthdays_only(self):
        bot = self.bot
        now = datetime(2026, 9, 7, 8, 1)
        with patch.object(bot, "_kyiv_now", return_value=now), \
             patch.object(bot, "load_state", return_value={}), \
             patch.object(bot, "check_schedule") as announcement, \
             patch.object(bot, "process_birthdays") as birthdays, \
             patch.object(bot, "check_replacements_screenshot") as replacements:
            bot.run_missed_tasks()
        announcement.assert_called_once_with(target_day=date(2026, 9, 7))
        birthdays.assert_called_once_with()
        replacements.assert_not_called()

    def test_weekday_evening_runs_missed_morning_and_replacement_jobs(self):
        bot = self.bot
        now = datetime(2026, 9, 7, 17, 1)
        with patch.object(bot, "_kyiv_now", return_value=now), \
             patch.object(bot, "load_state", return_value={}), \
             patch.object(bot, "check_schedule") as announcement, \
             patch.object(bot, "process_birthdays") as birthdays, \
             patch.object(bot, "check_replacements_screenshot") as replacements:
            bot.run_missed_tasks()
        announcement.assert_called_once_with(target_day=date(2026, 9, 7))
        birthdays.assert_called_once_with()
        replacements.assert_called_once_with()

    def test_weekend_runs_birthdays_but_not_weekday_jobs(self):
        bot = self.bot
        now = datetime(2026, 9, 6, 8, 1)
        with patch.object(bot, "_kyiv_now", return_value=now), \
             patch.object(bot, "load_state", return_value={}), \
             patch.object(bot, "check_schedule") as announcement, \
             patch.object(bot, "process_birthdays") as birthdays, \
             patch.object(bot, "check_replacements_screenshot") as replacements:
            bot.run_missed_tasks()
        announcement.assert_not_called()
        birthdays.assert_called_once_with()
        replacements.assert_not_called()

class ReplacementScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot
        cls.bot = bot

    def test_replacement_screenshot_uses_html_source_and_own_marker(self):
        bot = self.bot
        fake_driver = Mock()
        fake_driver.find_element.return_value.text = "T-32"
        manager = Mock()
        manager.return_value.install.return_value = "driver"
        waiter = Mock()
        html_url = bot.REPLACEMENTS_HTML_URL
        with patch.object(bot, "_kyiv_now", return_value=datetime(2026, 9, 7, 17, 1)), \
             patch.object(bot, "load_state", return_value={}), \
             patch.object(bot, "mark_replacements_checked") as mark, \
             patch.object(bot, "send_photo", return_value=True) as send_photo, \
             patch.object(bot.webdriver, "Chrome", return_value=fake_driver) as chrome, \
             patch.object(bot, "ChromeDriverManager", manager), \
             patch.object(bot, "WebDriverWait", return_value=waiter), \
             patch.object(bot, "SCHEDULE_GROUP", "T-32"):
            self.assertTrue(bot.check_replacements_screenshot())
        chrome.assert_called_once()
        fake_driver.get.assert_called_once_with(html_url)
        fake_driver.save_screenshot.assert_called_once()
        send_photo.assert_called_once()
        mark.assert_called_once_with(date(2026, 9, 7))
if __name__ == "__main__":
    unittest.main()


