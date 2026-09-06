# -*- coding: utf-8 -*-
"""Offline tests for the data-driven schedule parser."""

import unittest
import os
from datetime import date
from unittest.mock import patch

import schedule_announcements as schedule_data


class ScheduleParserTests(unittest.TestCase):
    def setUp(self):
        self.subject_rows = [
            ["Предмет", "Скорочення", "Посилання", "Викладач"],
            ["Комерційна діяльність та технологія торгівлі", "КД", "https://example.test/zoom", "Непочатова Г.В."],
            ["Облік, оподаткування та страхування в комерційній діяльності", "ООСвКД", "", "Попова І.А."],
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
            ["", "Т-32", "1", "ВІЛЬНА"],
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
        self.assertFalse(diagnostics["replacement_info"]["ignored"])


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


if __name__ == "__main__":
    unittest.main()
