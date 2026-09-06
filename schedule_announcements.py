# -*- coding: utf-8 -*-
"""Data-driven daily schedule announcements.

The module deliberately keeps schedule data out of Python.  It reads the
published CSV exports of the user's three Google Sheets tabs and overlays the
published replacement sheet by date, group and lesson number.
"""

import csv
import html
import io
import json
import os
import re
from datetime import date, datetime

import requests


DAY_NAMES = (
    "понеділок",
    "вівторок",
    "середа",
    "четвер",
    "п'ятниця",
    "субота",
    "неділя",
)

WEEK_LABELS = {
    "above": "над рискою",
    "below": "під рискою",
}

WINDOW_WORDS = {
    "---",
    "--",
    "-",
    "вільна",
    "вільно",
    "вікно",
    "немає",
    "відміна",
    "відмінено",
    "скасовано",
}

DATE_RANGE_RE = re.compile(
    r"(?P<d1>\d{1,2})[./-](?P<m1>\d{1,2})[./-](?P<y1>\d{4})"
    r"\s*[-–—]\s*"
    r"(?P<d2>\d{1,2})[./-](?P<m2>\d{1,2})[./-](?P<y2>\d{4})"
)
SINGLE_DATE_RE = re.compile(r"(?P<d>\d{1,2})[./-](?P<m>\d{1,2})[./-](?P<y>\d{4})")
TIME_RE = re.compile(r"^\s*(\d{1,2}:\d{2})(?:\s*[-–—]\s*(\d{1,2}:\d{2}))?")
GROUP_CELL_RE = re.compile(r"^[A-Za-zА-Яа-яІіЇїЄєҐґ]{1,10}\s*[-–—]?\s*\d{1,3}$")

# Transliteration used for group labels.  Keep the complete Ukrainian
# alphabet here: dropping an unmapped letter could cause a false match.
GROUP_TRANSLATION = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d",
    "е": "e", "є": "ye", "ж": "zh", "з": "z", "и": "y", "і": "i",
    "ї": "yi", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ь": "", "ю": "yu", "я": "ya",
    "ё": "yo", "ъ": "", "ы": "y", "э": "e",
})


class ScheduleDataError(RuntimeError):
    """Raised when a source is unavailable or structurally ambiguous."""


def clean(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def normalized(value):
    return re.sub(r"[^0-9a-zа-яіїєґ]", "", clean(value).casefold())


def normalized_group(value):
    return re.sub(r"[^a-z0-9]", "", clean(value).casefold().translate(GROUP_TRANSLATION))


def group_matches(value, target):
    """Match a group label while rejecting prefixes such as ``ПТ-32``."""
    target_norm = normalized_group(target)
    value_norm = normalized_group(value)
    if value_norm == target_norm:
        return True
    if not target_norm:
        return False
    return bool(re.search(r"(?<![a-z])" + re.escape(target_norm) + r"(?!\d)", value_norm))


def is_window(value):
    return normalized(value) in {normalized(item) for item in WINDOW_WORDS}


def fetch_csv(url, timeout=25):
    if not url:
        raise ScheduleDataError("CSV URL is not configured")
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = "utf-8"
    try:
        return list(csv.reader(io.StringIO(response.text.lstrip("\ufeff"))))
    except csv.Error as exc:
        raise ScheduleDataError("CSV parse failed: %s" % exc)


def _load_cache():
    path = os.getenv("SCHEDULE_CACHE_FILE", "schedule_cache.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_cache(cache):
    path = os.getenv("SCHEDULE_CACHE_FILE", "schedule_cache.json")
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def fetch_with_cache(url, cache_key):
    cache = _load_cache()
    try:
        rows = fetch_csv(url)
        cache[cache_key] = {"fetched_at": datetime.now().isoformat(), "rows": rows}
        _save_cache(cache)
        return rows, False
    except Exception as exc:
        cached = cache.get(cache_key, {})
        rows = cached.get("rows") if isinstance(cached, dict) else None
        if rows:
            return rows, True
        raise ScheduleDataError("%s source unavailable: %s" % (cache_key, exc))


def _column_index(header, names):
    wanted = {clean(name).casefold() for name in names}
    for index, value in enumerate(header):
        if clean(value).casefold() in wanted:
            return index
    return None


def parse_subjects(rows):
    for header in rows[:10]:
        subject_col = _column_index(header, ("Предмет",))
        if subject_col is not None:
            break
    else:
        raise ScheduleDataError("subjects sheet has no Предмет column")

    header = next(row for row in rows[:10] if _column_index(row, ("Предмет",)) is not None)
    subject_col = _column_index(header, ("Предмет",))
    alias_col = _column_index(header, ("Скорочення", "Абревіатура"))
    url_col = _column_index(header, ("Посилання", "URL", "Link"))
    teacher_col = _column_index(header, ("Викладач",))

    entries = []
    aliases = {}
    header_index = rows.index(header)
    for row in rows[header_index + 1:]:
        if subject_col >= len(row):
            continue
        subject = clean(row[subject_col])
        if not subject:
            continue
        entry = {
            "subject": subject,
            "alias": clean(row[alias_col]) if alias_col is not None and alias_col < len(row) else "",
            "url": clean(row[url_col]) if url_col is not None and url_col < len(row) else "",
            "teacher": clean(row[teacher_col]) if teacher_col is not None and teacher_col < len(row) else "",
        }
        entries.append(entry)
        for alias in (entry["subject"], entry["alias"]):
            key = normalized(alias)
            if key:
                aliases.setdefault(key, []).append(entry)
    return {"entries": entries, "aliases": aliases}


def resolve_subject(raw, directory):
    value = clean(raw)
    if not value or is_window(value):
        return {"subject": "Вікно", "url": "", "teacher": "", "known": True, "window": True}
    value_norm = normalized(value)
    candidates = directory["aliases"].get(value_norm, [])
    if len(candidates) == 1:
        entry = dict(candidates[0])
        entry.update({"known": True, "window": False})
        return entry

    # Replacement sheets often append a room/teacher or wrap the short name
    # in punctuation.  Accept a unique alias occurring as a whole token,
    # while keeping ambiguous abbreviations unresolved.
    token_candidates = []
    folded_value = value.casefold()
    for alias, entries in directory["aliases"].items():
        if len(alias) < 2:
            continue
        for entry in entries:
            alias_text = clean(entry.get("alias") or entry.get("subject", "")).casefold()
            if alias_text and re.search(r"(?<!\w)" + re.escape(alias_text) + r"(?!\w)", folded_value):
                token_candidates.append(entry)
    unique = {entry["subject"]: entry for entry in token_candidates}
    if len(unique) == 1:
        entry = dict(next(iter(unique.values())))
        entry.update({"known": True, "window": False})
        return entry
    return {"subject": value, "url": "", "teacher": "", "known": False, "window": False}


def _parse_single_date(value):
    match = SINGLE_DATE_RE.search(clean(value))
    if not match:
        return None
    try:
        return date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
    except ValueError:
        return None


def parse_semester(rows):
    if not rows:
        raise ScheduleDataError("semester sheet is empty")
    header = [clean(item).casefold() for item in rows[0]]
    columns = {}
    for index, value in enumerate(header):
        if "над" in value:
            columns[index] = "above"
        elif "під" in value:
            columns[index] = "below"
    if not columns:
        raise ScheduleDataError("semester sheet has no Над рискою/Під рискою columns")

    ranges = []
    for row in rows[1:]:
        for index, kind in columns.items():
            if index >= len(row):
                continue
            match = DATE_RANGE_RE.search(clean(row[index]))
            if not match:
                continue
            try:
                start = date(int(match.group("y1")), int(match.group("m1")), int(match.group("d1")))
                end = date(int(match.group("y2")), int(match.group("m2")), int(match.group("d2")))
            except ValueError as exc:
                raise ScheduleDataError("invalid semester date range") from exc
            if start > end:
                raise ScheduleDataError("semester range starts after it ends")
            ranges.append({"start": start, "end": end, "kind": kind})

    if not ranges:
        raise ScheduleDataError("semester sheet has no date ranges")
    ranges.sort(key=lambda item: item["start"])
    for previous, current in zip(ranges, ranges[1:]):
        if current["start"] <= previous["end"]:
            raise ScheduleDataError("semester ranges overlap")
    return ranges


def week_kind_for(day, ranges):
    matches = [item["kind"] for item in ranges if item["start"] <= day <= item["end"]]
    if len(matches) != 1:
        raise ScheduleDataError("no unambiguous semester week for %s" % day.isoformat())
    return matches[0]


def _parse_time(value):
    match = TIME_RE.match(clean(value))
    return (match.group(1), match.group(2) or "") if match else None


def parse_base_schedule(rows):
    weekday_columns = {}
    header_index = None
    for index, row in enumerate(rows[:20]):
        for column, value in enumerate(row):
            label = clean(value).casefold()
            if label in DAY_NAMES:
                weekday_columns[label] = column
        if len(weekday_columns) >= 2:
            header_index = index
            break
    if header_index is None:
        raise ScheduleDataError("schedule sheet has no weekday header")

    slots = []
    row_index = header_index + 1
    slot_number = 0
    while row_index < len(rows):
        row = rows[row_index]
        parsed_time = _parse_time(row[0] if row else "")
        if not parsed_time:
            row_index += 1
            continue
        slot_number += 1
        lower_row = rows[row_index + 1] if row_index + 1 < len(rows) else []
        upper = {}
        lower = {}
        for day_name, column in weekday_columns.items():
            upper[day_name] = clean(row[column]) if column < len(row) else ""
            lower[day_name] = clean(lower_row[column]) if column < len(lower_row) else ""
        slots.append({
            "number": slot_number,
            "start": parsed_time[0],
            "end": parsed_time[1],
            "upper": upper,
            "lower": lower,
        })
        row_index += 2
    if not slots:
        raise ScheduleDataError("schedule sheet has no time slots")
    return {"weekday_columns": weekday_columns, "slots": slots}


def _find_replacement_date(rows):
    for row in rows:
        for value in row:
            parsed = _parse_single_date(value)
            if parsed:
                return parsed
    return None


def _pair_number(value):
    match = re.fullmatch(r"\s*(\d{1,2})(?:\s*пара)?\s*", clean(value), re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_replacements(rows, target_day, group_name):
    source_day = _find_replacement_date(rows)
    if source_day != target_day:
        return {}, {"source_day": source_day, "ignored": True, "duplicates": []}

    replacements = {}
    duplicates = []
    current_group = None
    group_position = 0
    for row in rows:
        explicit_group_positions = [
            index for index, value in enumerate(row) if GROUP_CELL_RE.fullmatch(clean(value))
        ]
        if explicit_group_positions:
            group_position = explicit_group_positions[0]
            current_group = group_name if group_matches(row[group_position], group_name) else None
        elif any(clean(value) for value in row):
            # Continuation rows inherit the most recent explicit group.
            group_position = 0
        else:
            continue
        if current_group != group_name:
            continue

        pair_position = None
        pair_number = None
        for index in range(group_position + 1, min(len(row), group_position + 6)):
            candidate = _pair_number(row[index])
            if candidate is not None:
                pair_position, pair_number = index, candidate
                break
        if pair_position is None:
            continue
        subject_position = pair_position + 1
        raw_subject = clean(row[subject_position]) if subject_position < len(row) else ""
        if not raw_subject:
            continue

        teacher = ""
        # In the published replacement layout the teacher is normally two
        # columns after the subject (the column between them is a room/type).
        preferred_teacher_position = subject_position + 2
        if preferred_teacher_position < len(row):
            candidate = clean(row[preferred_teacher_position])
            if candidate and not TIME_RE.match(candidate):
                teacher = candidate
        for index in range(subject_position + 1, min(len(row), subject_position + 5)):
            if teacher:
                break
            candidate = clean(row[index])
            if candidate and not TIME_RE.match(candidate) and candidate not in {"1 пара", "2 пара", "3 пара", "4 пара", "5 пара"}:
                teacher = candidate
                break
        replacement = {"raw_subject": raw_subject, "teacher": teacher, "pair": pair_number}
        if pair_number in replacements:
            duplicates.append(pair_number)
        replacements[pair_number] = replacement

    return replacements, {"source_day": source_day, "ignored": False, "duplicates": sorted(set(duplicates))}


def _published_csv_fallback(url):
    if not url:
        return ""
    marker = "/pubhtml"
    if marker in url and "/d/e/" in url:
        return url.split(marker, 1)[0] + "/pub?output=csv&gid=0"
    return url


def _config():
    replacements_url = os.getenv("REPLACEMENTS_CSV_URL") or _published_csv_fallback(os.getenv("SCHEDULE_URL", ""))
    return {
        "base": os.getenv("BASE_SCHEDULE_CSV_URL", ""),
        "subjects": os.getenv("SUBJECTS_CSV_URL", ""),
        "semester": os.getenv("SEMESTER_CSV_URL", ""),
        "replacements": replacements_url,
        "group": os.getenv("SCHEDULE_GROUP", ""),
    }


def build_daily_announcement(target_day=None):
    target_day = target_day or datetime.now().date()
    config = _config()
    missing = [key for key in ("base", "subjects", "semester", "replacements", "group") if not config[key]]
    if missing:
        raise ScheduleDataError("missing schedule configuration: " + ", ".join(missing))

    base_rows, base_stale = fetch_with_cache(config["base"], "base")
    subject_rows, subjects_stale = fetch_with_cache(config["subjects"], "subjects")
    semester_rows, semester_stale = fetch_with_cache(config["semester"], "semester")
    replacement_rows, replacements_stale = fetch_with_cache(config["replacements"], "replacements")

    directory = parse_subjects(subject_rows)
    base = parse_base_schedule(base_rows)
    semester_ranges = parse_semester(semester_rows)
    week_kind = week_kind_for(target_day, semester_ranges)
    replacements, replacement_info = parse_replacements(replacement_rows, target_day, config["group"])

    weekday = DAY_NAMES[target_day.weekday()]
    slots_for_day = []
    for slot in base["slots"]:
        upper = slot["upper"].get(weekday, "")
        lower = slot["lower"].get(weekday, "")
        if not upper and lower:
            raw_subject = lower
        elif not lower or week_kind == "above":
            raw_subject = upper
        else:
            raw_subject = lower
        item = resolve_subject(raw_subject, directory)
        replacement = replacements.get(slot["number"])
        if replacement:
            item = resolve_subject(replacement["raw_subject"], directory)
            if replacement.get("teacher"):
                item["teacher"] = replacement["teacher"]
            item["replacement"] = True
        else:
            item["replacement"] = False
        item.update({"number": slot["number"], "start": slot["start"], "end": slot["end"]})
        slots_for_day.append(item)

    # Do not silently drop a replacement for a newly-added lesson slot.
    known_numbers = {slot["number"] for slot in slots_for_day}
    for number, replacement in sorted(replacements.items()):
        if number not in known_numbers:
            item = resolve_subject(replacement["raw_subject"], directory)
            item.update({"number": number, "start": "", "end": "", "replacement": True})
            if replacement.get("teacher"):
                item["teacher"] = replacement["teacher"]
            slots_for_day.append(item)

    lines = [
        "📅 <b>Розклад на %s, %s</b>" % (weekday.capitalize(), target_day.strftime("%d.%m.%Y")),
        "👥 Група: <b>%s</b> • %s" % (html.escape(config["group"]), WEEK_LABELS[week_kind]),
        "",
    ]
    unknown = []
    for item in slots_for_day:
        time_label = item["start"] or ("пара %s" % item["number"])
        if item["end"]:
            time_label += "–" + item["end"]
        prefix = "🔄 " if item.get("replacement") else ""
        if item.get("window"):
            label = "🪟 Вікно"
        else:
            label = html.escape(item["subject"])
            if not item.get("known"):
                unknown.append(item["subject"])
        lines.append("<b>%s</b> — %s%s" % (html.escape(time_label), prefix, label))
        if item.get("teacher"):
            lines.append("    👨‍🏫 %s" % html.escape(item["teacher"]))
        if item.get("url"):
            lines.append('    🔗 <a href="%s">Онлайн-заняття</a>' % html.escape(item["url"], quote=True))

    warnings = []
    if base_stale or subjects_stale or semester_stale or replacements_stale:
        stale = [name for name, value in (("розклад", base_stale), ("предмети", subjects_stale), ("семестр", semester_stale), ("заміни", replacements_stale)) if value]
        warnings.append("⚠️ Використано кеш: " + ", ".join(stale))
    if replacement_info.get("ignored"):
        warnings.append("ℹ️ Для цієї дати у таблиці замін записів не знайдено.")
    elif not replacements:
        warnings.append("ℹ️ Для групи %s замін на цю дату не знайдено." % html.escape(config["group"]))
    if replacement_info.get("duplicates"):
        warnings.append("⚠️ Дубльовані заміни для пар: " + ", ".join(map(str, replacement_info["duplicates"])))
    if unknown:
        warnings.append("⚠️ Невідомі скорочення: " + ", ".join(sorted(set(unknown))))
    if warnings:
        lines.extend(["", *warnings])

    return "\n".join(lines), {
        "target_day": target_day,
        "week_kind": week_kind,
        "replacement_info": replacement_info,
        "stale": bool(base_stale or subjects_stale or semester_stale or replacements_stale),
        "unknown_subjects": sorted(set(unknown)),
    }
