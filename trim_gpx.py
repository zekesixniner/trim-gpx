#!/usr/bin/env python3
"""
trim_gpx.py - fit GPS tracks to GoPro clips.

Two jobs:

  Cut a track down to exactly one clip, e.g. a Flightradar24 export for a clip
  the camera recorded without GPS:

      trim_gpx.py TRACK OUTPUT --video GS010132.360

  Check the GPX extracted from each clip against the clip itself, and fill
  what is missing from another track - SkyDemon first, Flightradar24 second -
  while the camera's own points stay wherever it has them:

      trim_gpx.py --check [GS010130.gpx | FOLDER ...]

Reads every timestamped point: <trkpt>, <wpt> and <rtept> in GPX 1.0/1.1
(also gpsbabel output, where the timed points are <wpt>), Placemark/TimeStamp
and gx:Track in KML, and Flightradar24's CSV export. Measured speed and course
come along when the source has them and are written to every point as a
Garmin TrackPointExtension (speed in m/s, course in degrees). OVRLEY then uses
that speed instead of deriving it from positions with whole-second timestamps.

A Flightradar24 KML or CSV it reads is also saved as GPX beside it
(4229ad6f.csv -> 4229ad6f.gpx) by gpsbabel, for other programs.

See README.md and MANUAL.md; run with --help for the options.
Svenska utskrifter: --lang sv, eller GOPRO_LANG=sv.
"""
import argparse
import bisect
import csv
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

__version__ = "1.2.0"

# --------------------------------------------------------------------------- #
# messages (EN/SV, --lang or GOPRO_LANG like gopro-max-gpx-pipeline)
# --------------------------------------------------------------------------- #
MESSAGES = {
    "en": {
        "source": "Source:   {n} timestamped points, {first}Z – {last}Z",
        "video": "Video:    {name}: creation_time {ct}, length {dur} s",
        "chapter_offset": "          chapter {ch} of recording {num}: its creation_time is the "
                          "recording's start, adding the {n} earlier chapter(s) ({sec} s)",
        "chapter_unknown": "[WARNING] {name} is chapter {ch} of a recording, but the earlier "
                           "chapters are not next to it. If its creation_time is the start of "
                           "the whole recording, the window is too early: add their length to "
                           "--start.",
        "window": "Window:   {start}Z – {end}Z ({dur} s)",
        "outside": "[ERROR]   The window lies entirely outside the track.",
        "tz_fits": "          {how} the window lands at {a}Z – {b}Z, fully inside the track.",
        "tz_without": "Without --tz",
        "tz_with": "With --tz {tz}",
        "tz_none": "          Neither --tz 0, 1 nor 2 puts the window inside the track - "
                   "check the start time and date.",
        "partial": "[WARNING] The track only covers {a}Z – {b}Z of the window.",
        "in_window": "In window: {n} source points, largest gap between points {gap} s",
        "altitude": "Altitude: {lo:.0f}–{hi:.0f} m ({lo_ft:.0f}–{hi_ft:.0f} ft)",
        "speed_measured": "Speed:    {lo:.0f}–{hi:.0f} kt (measured in the source, written to the GPX)",
        "speed_derived": "Speed:    {lo:.0f}–{hi:.0f} kt (derived from the positions)",
        "course": "Course:   {a:03.0f}° → {b:03.0f}°",
        "saved": "\n✅ Saved {n} points → {out}",
        "err_args": "give --video, or both --start and --duration",
        "err_duration": "--duration must be longer than 0 s",
        "err_hz": "--hz cannot be negative",
        "err_points": "[ERROR]   Found fewer than two timestamped points in {path}.",
        "err_read": "[ERROR]   Could not read {path}: {err}",
        "err_csv_layout": "no time and position columns (expected Flightradar24's "
                          "Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction)",
        "err_csv_row": "line {line}: {err}",
        "err_time": "unknown time format: {s!r}",
        "err_start": "[ERROR]   --start: {err}",
        "err_ffprobe_missing": "[ERROR]   ffprobe not found ({ffprobe}). Install ffmpeg, "
                               "or give --start and --duration.",
        "err_ffprobe": "[ERROR]   ffprobe could not read {path}: {err}",
        "err_no_ct": "[ERROR]   {path} has no creation_time. Give --start.",
        "err_no_dur": "[ERROR]   {path} has no duration. Give --duration.",
        # --check
        "usage_trim": "give TRACK and OUTPUT, or use --check",
        "err_needs_check": "{opt} works with --check",
        "chk_ffprobe_missing": "ffprobe not found ({ffprobe}); install ffmpeg (sudo apt install ffmpeg)",
        "chk_no_ct": "{video} has no creation_time",
        "chk_no_dur": "{video} has no duration",
        "err_check_one": "{opt} works with one clip at a time",
        "err_check_trim": "{opt} belongs to cutting a track (TRACK OUTPUT), not to --check",
        "err_no_clips": "[ERROR]   No camera GPX (like GS010130.gpx) in {where}.",
        "check_head": "Checking {n} clip(s){where}:",
        "check_where": ", videos in {dir}",
        "st_complete": "complete",
        "st_missing": "missing",
        "st_nogps": "no GPS",
        "st_error": "error",
        "row_complete": "{dur} s, largest gap {gap} s",
        "row_missing": "{miss} s of {dur} s: {spans}",
        "row_nogps": "{dur} s",
        "row_filled": "; {sec} s filled earlier from {src}",
        "row_clock": " · camera clock {off} s",
        "no_video": "no video {stem}.360 or .mp4 in {dirs} (give --video-dir)",
        "clock_moved": "[WARNING] {name}: the camera clock is {off} s off GPS time, so the "
                       "window follows GPS time: {start}Z. In OVRLEY, set the sync offset to 0.",
        "mp4_video": "[WARNING] {name}: timed by {video}, not the camera's .360 - check that its "
                     "creation_time is the camera's, or give --video-dir with the .360 files.",
        "gap_head": "\n{name}: missing {spans} ({miss} s of {dur} s)",
        "cand_head": "  Fill from:",
        "cand_row": "    {i}  {name}  {kind}  covers {cov} s of {miss} s",
        "ask_choose": "  Choose 1–{n} (Enter = 1), another file, or n to leave the gap: ",
        "ask_file": "  File to fill from (SkyDemon or Flightradar24: GPX, KML or CSV), "
                    "or Enter to leave the gap: ",
        "fill_nothing": "  {name} has no data for the missing time.",
        "fill_bad": "  Could not use {name}: {err}",
        "fill_done": "  ✓ {sec} s from {src} ({n} points){match}",
        "match_full": "; matched to the camera: altitude {ele}, position {pos} m",
        "match_alt": "; altitude matched to the camera's GPS ({ele}, from {ref})",
        "match_none": "; altitude not matched (no camera GPS on this flight nearby): "
                      "it comes straight from {src}",
        "ref_self": "this clip",
        "still_missing": "  still missing: {spans} ({sec} s)",
        "left_as_is": "  The gap is left as it is.",
        "updated": "  ✅ {name} updated: {cam} camera points + {fill} filled "
                   "(original: {orig})",
        "updated_to": "  ✅ Saved {n} points ({cam} camera + {fill} filled) → {out}",
        "dry_run": "  (--dry-run: nothing is filled or written)",
        "sum_ok": "\nEvery clip has data for its whole length ({n} checked).",
        "sum_left": "\n{k} of {n} clip(s) still have missing data.",
        "sum_err": "{k} clip(s) could not be checked.",
        "kind_skydemon": "SkyDemon",
        "kind_fr24": "Flightradar24",
        "kind_other": "GPS track",
        # Flightradar24 KML/CSV saved as GPX
        "gpx_saved": "Saved as GPX: {src} → {out} ({n} points, gpsbabel)",
        "gpx_kept": "[WARNING] {out} was not made by gpsbabel, so {src} is not saved as GPX "
                    "over it.",
        "gpx_no_gpsbabel": "[WARNING] gpsbabel not found ({gpsbabel}), so {src} is not saved as "
                           "GPX. Install it: sudo apt install gpsbabel",
        "gpx_failed": "[WARNING] gpsbabel could not save {src} as GPX: {err}",
    },
    "sv": {
        "source": "Källa:    {n} tidsstämplade punkter, {first}Z – {last}Z",
        "video": "Video:    {name}: creation_time {ct}, längd {dur} s",
        "chapter_offset": "          kapitel {ch} av inspelning {num}: dess creation_time är "
                          "inspelningens start, lägger till {n} tidigare kapitel ({sec} s)",
        "chapter_unknown": "[VARNING] {name} är kapitel {ch} av en inspelning, men de tidigare "
                           "kapitlen ligger inte bredvid. Är dess creation_time hela "
                           "inspelningens start blir fönstret för tidigt: lägg till deras längd "
                           "i --start.",
        "window": "Fönster:  {start}Z – {end}Z ({dur} s)",
        "outside": "[FEL]     Fönstret ligger helt utanför spåret.",
        "tz_fits": "          {how} hamnar fönstret {a}Z – {b}Z, helt inuti spåret.",
        "tz_without": "Utan --tz",
        "tz_with": "Med --tz {tz}",
        "tz_none": "          Varken --tz 0, 1 eller 2 lägger fönstret inuti spåret - "
                   "kontrollera starttid och datum.",
        "partial": "[VARNING] Spåret täcker bara {a}Z – {b}Z av fönstret.",
        "in_window": "I fönstret: {n} källpunkter, största glapp mellan punkter {gap} s",
        "altitude": "Höjd:     {lo:.0f}–{hi:.0f} m ({lo_ft:.0f}–{hi_ft:.0f} ft)",
        "speed_measured": "Markfart: {lo:.0f}–{hi:.0f} kt (uppmätt i källan, skrivs med)",
        "speed_derived": "Markfart: {lo:.0f}–{hi:.0f} kt (framräknad ur positionerna)",
        "course": "Kurs:     {a:03.0f}° → {b:03.0f}°",
        "saved": "\n✅ Sparade {n} punkter → {out}",
        "err_args": "ange --video, eller både --start och --duration",
        "err_duration": "--duration måste vara längre än 0 s",
        "err_hz": "--hz kan inte vara negativ",
        "err_points": "[FEL]     Hittade färre än två tidsstämplade punkter i {path}.",
        "err_read": "[FEL]     Kunde inte läsa {path}: {err}",
        "err_csv_layout": "hittar inga kolumner för tid och position (väntade Flightradar24:s "
                          "Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction)",
        "err_csv_row": "rad {line}: {err}",
        "err_time": "okänt tidsformat: {s!r}",
        "err_start": "[FEL]     --start: {err}",
        "err_ffprobe_missing": "[FEL]     Hittar inte ffprobe ({ffprobe}). Installera ffmpeg, "
                               "eller ange --start och --duration.",
        "err_ffprobe": "[FEL]     ffprobe kunde inte läsa {path}: {err}",
        "err_no_ct": "[FEL]     {path} saknar creation_time. Ange --start.",
        "err_no_dur": "[FEL]     {path} saknar längd. Ange --duration.",
        # --check
        "usage_trim": "ange SPÅR och UTDATA, eller använd --check",
        "err_needs_check": "{opt} fungerar med --check",
        "chk_ffprobe_missing": "hittar inte ffprobe ({ffprobe}); installera ffmpeg (sudo apt install ffmpeg)",
        "chk_no_ct": "{video} saknar creation_time",
        "chk_no_dur": "{video} saknar längd",
        "err_check_one": "{opt} fungerar med ett klipp i taget",
        "err_check_trim": "{opt} hör till klippning av ett spår (SPÅR UTDATA), inte till --check",
        "err_no_clips": "[FEL]     Ingen kamera-GPX (som GS010130.gpx) i {where}.",
        "check_head": "Kontrollerar {n} klipp{where}:",
        "check_where": ", videor i {dir}",
        "st_complete": "komplett",
        "st_missing": "saknas",
        "st_nogps": "ingen GPS",
        "st_error": "fel",
        "row_complete": "{dur} s, största glapp {gap} s",
        "row_missing": "{miss} s av {dur} s: {spans}",
        "row_nogps": "{dur} s",
        "row_filled": "; {sec} s ifyllt tidigare från {src}",
        "row_clock": " · kamerans klocka {off} s",
        "no_video": "ingen video {stem}.360 eller .mp4 i {dirs} (ange --video-dir)",
        "clock_moved": "[VARNING] {name}: kamerans klocka går {off} s fel mot GPS-tiden, så "
                       "fönstret följer GPS-tiden: {start}Z. Sätt synkoffseten till 0 i OVRLEY.",
        "mp4_video": "[VARNING] {name}: tiden tas från {video}, inte kamerans .360 - kontrollera "
                     "att dess creation_time är kamerans, eller ange --video-dir med .360-filerna.",
        "gap_head": "\n{name}: saknar {spans} ({miss} s av {dur} s)",
        "cand_head": "  Fyll från:",
        "cand_row": "    {i}  {name}  {kind}  täcker {cov} s av {miss} s",
        "ask_choose": "  Välj 1–{n} (Enter = 1), en annan fil, eller n för att lämna luckan: ",
        "ask_file": "  Fil att fylla från (SkyDemon eller Flightradar24: GPX, KML eller CSV), "
                    "eller Enter för att lämna luckan: ",
        "fill_nothing": "  {name} har inga data för den tid som saknas.",
        "fill_bad": "  Kunde inte använda {name}: {err}",
        "fill_done": "  ✓ {sec} s från {src} ({n} punkter){match}",
        "match_full": "; matchat mot kameran: höjd {ele}, position {pos} m",
        "match_alt": "; höjden matchad mot kamerans GPS ({ele}, från {ref})",
        "match_none": "; höjden inte matchad (ingen kamera-GPS från flygningen i närheten): "
                      "den kommer direkt från {src}",
        "ref_self": "detta klipp",
        "still_missing": "  saknas fortfarande: {spans} ({sec} s)",
        "left_as_is": "  Luckan lämnas som den är.",
        "updated": "  ✅ {name} uppdaterad: {cam} kamerapunkter + {fill} ifyllda "
                   "(originalet: {orig})",
        "updated_to": "  ✅ Sparade {n} punkter ({cam} kamera + {fill} ifyllda) → {out}",
        "dry_run": "  (--dry-run: inget fylls i eller skrivs)",
        "sum_ok": "\nAlla klipp har data för hela sin längd (kontrollerade: {n}).",
        "sum_left": "\n{k} av {n} klipp saknar fortfarande data.",
        "sum_err": "{k} klipp kunde inte kontrolleras.",
        "kind_skydemon": "SkyDemon",
        "kind_fr24": "Flightradar24",
        "kind_other": "GPS-spår",
        # Flightradar24:s KML/CSV sparad som GPX
        "gpx_saved": "Sparad som GPX: {src} → {out} ({n} punkter, gpsbabel)",
        "gpx_kept": "[VARNING] {out} är inte gjord av gpsbabel, så {src} sparas inte som GPX "
                    "över den.",
        "gpx_no_gpsbabel": "[VARNING] Hittar inte gpsbabel ({gpsbabel}), så {src} sparas inte "
                           "som GPX. Installera det: sudo apt install gpsbabel",
        "gpx_failed": "[VARNING] gpsbabel kunde inte spara {src} som GPX: {err}",
    },
}
LANG = "en"


def default_lang():
    env = os.environ.get("GOPRO_LANG", "en").lower()
    return env if env in MESSAGES else "en"


def t(key, **kw):
    return MESSAGES.get(LANG, MESSAGES["en"]).get(key, MESSAGES["en"][key]).format(**kw)


class TrimError(Exception):
    """An error with a message key, printed in the chosen language."""

    def __init__(self, key, **kw):
        super().__init__(key)
        self.key, self.kw = key, kw

    def text(self):
        return t(self.key, **self.kw)


def die(key, code=1, **kw):
    sys.stdout.flush()
    print(t(key, **kw), file=sys.stderr)
    sys.exit(code)


# --------------------------------------------------------------------------- #
# points and time
# --------------------------------------------------------------------------- #
# spd = speed in m/s, crs = course in degrees, src = where a filled point came
# from (written as <src>); None when absent
Pt = namedtuple("Pt", "t lat lon ele spd crs src", defaults=(None, None, None))
# kind: camera, skydemon, fr24, trim (written by this script) or other
Track = namedtuple("Track", "path pts times kind creator")

KT = 0.514444  # m/s per knot
FT = 0.3048    # m per foot
SPEED_UNITS = {"kt": KT, "kts": KT, "knots": KT, "km/h": 1 / 3.6, "mph": 0.44704, "m/s": 1.0}

DT_RE = re.compile(
    r"^(\d{4})[-:](\d{2})[-:](\d{2})[T ](\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)"
    r"\s*(Z|[+-]\d{2}:?\d{2})?$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$")
EPOCH_RE = re.compile(r"^\d+(?:\.\d+)?$")
TAG_RE = re.compile(r"<[^>]*>")
DESC_SPEED_RE = re.compile(r"Speed:\s*([\d.,]+)\s*(kts|kt|knots|km/h|mph|m/s)", re.I)
DESC_HEADING_RE = re.compile(r"(?:Heading|Track|Course):\s*([\d.]+)", re.I)
# GoPro file names: GS/GX/GH + 2-digit chapter + 4-digit file number
CHAPTER_RE = re.compile(r"^(G[HSX])(\d{2})(\d{4})$", re.I)
CLIP_PREFIX_RE = re.compile(r"^G[HSX]\d{6}", re.I)          # also GS010130.virb.gpx
CAMERA_GPX_RE = re.compile(r"^G[HSX]\d{6}\.gpx$", re.I)


def parse_dt(s):
    """ISO/exiftool time → UTC. Without a time zone the time is taken as UTC."""
    m = DT_RE.match(s.strip())
    if not m:
        raise TrimError("err_time", s=s)
    y, mo, d, h, mi, sec, tz = m.groups()
    dt = datetime(int(y), int(mo), int(d), int(h), int(mi), tzinfo=timezone.utc)
    dt += timedelta(seconds=float(sec))
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        tz = tz[1:].replace(":", "")
        dt -= sign * timedelta(hours=int(tz[:2]), minutes=int(tz[2:]))
    return dt


def parse_duration(s):
    secs = 0.0
    for part in s.strip().split(":"):
        secs = secs * 60 + float(part)
    return secs


def fmt_secs(x):
    return f"{x:.3f}".rstrip("0").rstrip(".")


def secs(a, b):
    return (b - a).total_seconds()


# --------------------------------------------------------------------------- #
# reading tracks
# --------------------------------------------------------------------------- #
def local(tag):
    return tag.rsplit("}", 1)[-1]


def kids(el, name):
    return [c for c in el if local(c.tag) == name]


def kid(el, name):
    k = kids(el, name)
    return k[0] if k else None


def descendant(el, *names):
    """First element below el (el itself not counted) with one of the names."""
    return next((e for e in el.iter() if e is not el and local(e.tag) in names), None)


def number(el):
    try:
        v = float(el.text)
    except (AttributeError, TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def no_fix(el):
    """<fix>none</fix>, or a numeric fix of 0: the point has no position."""
    if el is None:
        return False
    text = (el.text or "").strip().lower()
    return text == "none" or number(el) == 0


def text_speed_course(*elements):
    """Speed (m/s) and course (degrees) from Flightradar24's point description
    ("Speed: 90 kt", "Heading: 39°"), which gpsbabel keeps as text in <desc>/<cmt>."""
    text = " ".join(TAG_RE.sub(" ", e.text or "") for e in elements if e is not None)
    m = DESC_SPEED_RE.search(text)
    spd = float(m.group(1).replace(",", "")) * SPEED_UNITS[m.group(2).lower()] if m else None
    m = DESC_HEADING_RE.search(text)
    return spd, float(m.group(1)) if m else None


def kml_speed_course(placemark):
    """Speed (m/s) and course (degrees) from a Flightradar24-style Placemark."""
    spd, crs = text_speed_course(kid(placemark, "description"))
    icon = descendant(placemark, "IconStyle")
    heading = number(kid(icon, "heading")) if icon is not None else None
    return spd, heading if heading is not None else crs


def read_xml(root):
    """Timestamped points, and how many of them took their speed from a
    Flightradar24-style description."""
    pts, described = [], 0
    for el in root.iter():
        name = local(el.tag)
        if name in ("trkpt", "wpt", "rtept"):            # GPX
            tm = kid(el, "time")
            if tm is None or not (tm.text or "").strip() or no_fix(kid(el, "fix")):
                continue
            ele = kid(el, "ele")
            # GPX 1.0 has <speed>/<course> directly, GPX 1.1 in <extensions>;
            # gpsbabel output of a Flightradar24 KML has them only as text
            spd = number(descendant(el, "speed"))
            crs = number(descendant(el, "course", "heading"))
            if spd is None or crs is None:
                d_spd, d_crs = text_speed_course(kid(el, "desc"), kid(el, "cmt"))
                described += d_spd is not None and spd is None
                spd = d_spd if spd is None else spd
                crs = d_crs if crs is None else crs
            src = kid(el, "src")
            pts.append(Pt(parse_dt(tm.text), float(el.get("lat")), float(el.get("lon")),
                          float(ele.text) if ele is not None and ele.text else None,
                          spd, crs, (src.text or "").strip() or None if src is not None else None))
        elif name == "Placemark":                         # KML, one point per Placemark
            ts = next((e for e in el.iter() if local(e.tag) == "TimeStamp"), None)
            pt = next((e for e in el.iter() if local(e.tag) == "Point"), None)
            when = kid(ts, "when") if ts is not None else None
            coords = kid(pt, "coordinates") if pt is not None else None
            if when is None or coords is None:
                continue
            c = coords.text.strip().split(",")
            spd, crs = kml_speed_course(el)
            described += spd is not None
            pts.append(Pt(parse_dt(when.text), float(c[1]), float(c[0]),
                          float(c[2]) if len(c) > 2 else None, spd, crs))
        elif name == "Track":                             # KML gx:Track
            for w, c in zip(kids(el, "when"), kids(el, "coord")):
                v = c.text.split()
                pts.append(Pt(parse_dt(w.text), float(v[1]), float(v[0]),
                              float(v[2]) if len(v) > 2 else None))
    return pts, described


def read_csv(path):
    """Flightradar24 CSV: Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction.

    Altitude is in feet and speed in knots, as Flightradar24 writes them. Also
    takes separate Latitude/Longitude columns and an ISO time in Timestamp.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    head = [h.strip().lower() for h in rows[0]]

    def col(*names):
        return next((head.index(n) for n in names if n in head), None)

    c_iso = col("utc", "time", "datetime")
    c_ts = col("timestamp", "epoch")
    c_pos = col("position")
    c_lat, c_lon = col("latitude", "lat"), col("longitude", "lon", "lng")
    c_alt = col("altitude", "alt")
    c_spd = col("speed", "gspeed", "groundspeed", "ground_speed")
    c_dir = col("direction", "heading", "track", "course")
    if (c_iso is None and c_ts is None) or (c_pos is None and (c_lat is None or c_lon is None)):
        raise TrimError("err_csv_layout")

    def cell(r, c):
        return r[c].strip() if c is not None and c < len(r) else ""

    def num(r, c, scale=1.0):
        v = cell(r, c)
        return float(v) * scale if v else None

    pts = []
    for line, r in enumerate(rows[1:], start=2):
        if not any(x.strip() for x in r):
            continue
        try:
            iso, ts = cell(r, c_iso), cell(r, c_ts)
            if iso:
                when = parse_dt(iso)
            elif EPOCH_RE.match(ts):
                when = datetime.fromtimestamp(float(ts), timezone.utc)
            else:
                when = parse_dt(ts)
            if c_pos is not None:
                lat, lon = (float(x) for x in cell(r, c_pos).split(",")[:2])
            else:
                lat, lon = float(cell(r, c_lat)), float(cell(r, c_lon))
            pts.append(Pt(when, lat, lon, num(r, c_alt, FT), num(r, c_spd, KT), num(r, c_dir)))
        except TrimError as e:
            raise TrimError("err_csv_row", line=line, err=e.text()) from None
        except ValueError as e:
            raise TrimError("err_csv_row", line=line, err=e) from None
    return pts


def load_track(path):
    """Read a track and guess what made it."""
    path = Path(path)
    kind, creator, root = "other", "", None
    if path.suffix.lower() != ".csv":
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                first_line = f.readline()
            if "," not in first_line:
                raise
    if root is None:
        pts = read_csv(path)
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            head = f.readline().lower()
        if "callsign" in head and "position" in head:
            kind = "fr24"
    else:
        creator = root.get("creator") or ""
        pts, described = read_xml(root)
        c = creator.lower()
        if "skydemon" in c:
            kind = "skydemon"
        elif "trim_gpx" in c:
            kind = "trim"
        elif "gopro-telemetry" in c or CLIP_PREFIX_RE.match(path.name):
            kind = "camera"
        elif described:
            kind = "fr24"
    pts.sort(key=lambda p: p.t)
    uniq = []
    for p in pts:
        if not uniq or p.t != uniq[-1].t:
            uniq.append(p)
    return Track(path, uniq, [p.t for p in uniq], kind, creator)


def read_points(path):
    return load_track(path).pts


# --------------------------------------------------------------------------- #
# the clip: ffprobe and GoPro chapters
# --------------------------------------------------------------------------- #
def probe(ffprobe, path):
    """(creation_time as UTC datetime or None, duration in s or None).
    Raises TrimError when ffprobe is missing or cannot read the file."""
    cmd = [ffprobe, "-v", "error", "-show_entries",
           "format=duration:format_tags=creation_time", "-of", "json", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise TrimError("err_ffprobe_missing", ffprobe=ffprobe) from None
    if r.returncode != 0:
        lines = (r.stderr or "").strip().splitlines()
        raise TrimError("err_ffprobe", path=path, err=lines[-1] if lines else f"exit {r.returncode}")
    fmt = json.loads(r.stdout or "{}").get("format", {})
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    ct, dur = tags.get("creation_time"), fmt.get("duration")
    try:
        return (parse_dt(ct) if ct else None), (float(dur) if dur not in (None, "N/A") else None)
    except TrimError as e:
        raise TrimError("err_ffprobe", path=path, err=e.text()) from None


def bare(text):
    """A message without its [ERROR]/[FEL] prefix, for a line in the --check table."""
    return re.sub(r"^\[[^\]]*\]\s*", "", text)


def video_window(ffprobe, path):
    """Start and length of the clip; chapter 2+ of a recording is corrected when
    its creation_time turns out to be the start of the whole recording."""
    path = Path(path)
    ct, dur = probe(ffprobe, path)
    start, notes = ct, []
    m = CHAPTER_RE.match(path.stem)
    if ct is not None and m and int(m.group(2)) > 1:
        pre, ch, num = m.group(1), int(m.group(2)), m.group(3)
        earlier = [path.with_name(f"{pre}{c:02d}{num}{path.suffix}") for c in range(1, ch)]
        if all(e.exists() for e in earlier):
            if probe(ffprobe, earlier[0])[0] == ct:
                off = sum(probe(ffprobe, e)[1] or 0.0 for e in earlier)
                start = ct + timedelta(seconds=off)
                notes.append(("chapter_offset", dict(ch=ch, num=num, n=len(earlier),
                                                     sec=fmt_secs(off))))
        else:
            notes.append(("chapter_unknown", dict(name=path.name, ch=ch)))
    return ct, start, dur, notes


# --------------------------------------------------------------------------- #
# interpolation and output
# --------------------------------------------------------------------------- #
def lerp(a, b, f):
    return None if a is None or b is None else a + f * (b - a)


def lerp_deg(a, b, f):
    if a is None or b is None:
        return None
    return (a + f * ((b - a + 540) % 360 - 180)) % 360


def interp(pts, times, t):
    """Linear interpolation at time t (times[0] <= t <= times[-1])."""
    i = bisect.bisect_left(times, t)
    if i < len(pts) and times[i] == t:
        return pts[i]
    a, b = pts[i - 1], pts[i]
    f = (t - a.t) / (b.t - a.t)
    return Pt(t, a.lat + f * (b.lat - a.lat), a.lon + f * (b.lon - a.lon),
              lerp(a.ele, b.ele, f), lerp(a.spd, b.spd, f), lerp_deg(a.crs, b.crs, f),
              a.src if a.src == b.src else None)


def cut(pts, times, s, e, hz=0.0):
    """The points from s to e, with the first and last interpolated onto s and e."""
    if hz > 0:
        step = 1.0 / hz
        n = int(math.floor((e - s).total_seconds() / step + 1e-9))
        ts = [s + timedelta(seconds=k * step) for k in range(n + 1)]
        if (e - ts[-1]).total_seconds() > 1e-3:
            ts.append(e)
        return [interp(pts, times, x) for x in ts]
    return ([interp(pts, times, s)]
            + [p for p in pts if s < p.t < e]
            + [interp(pts, times, e)])


def dist_m(a, b):
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dl = math.radians(b.lon - a.lon)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def fmt_time(t):
    if t.microsecond:
        return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_gpx(path, pts, name):
    tpx = any(p.spd is not None or p.crs is not None for p in pts)
    ns = (' xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v2"'
          if tpx else "")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<gpx version="1.1" creator="trim_gpx.py" xmlns="http://www.topografix.com/GPX/1/1"{ns}>',
             '  <trk>', f'    <name>{escape(name)}</name>', '    <trkseg>']
    for p in pts:
        ele = f"<ele>{p.ele:.1f}</ele>" if p.ele is not None else ""
        src = f"<src>{escape(p.src)}</src>" if p.src else ""
        ext = ""
        if p.spd is not None or p.crs is not None:
            ext = ("<extensions><gpxtpx:TrackPointExtension>"
                   + (f"<gpxtpx:speed>{p.spd:.2f}</gpxtpx:speed>" if p.spd is not None else "")
                   + (f"<gpxtpx:course>{p.crs % 360:.1f}</gpxtpx:course>" if p.crs is not None else "")
                   + "</gpxtpx:TrackPointExtension></extensions>")
        lines.append(f'      <trkpt lat="{p.lat:.7f}" lon="{p.lon:.7f}">{ele}'
                     f'<time>{fmt_time(p.t)}</time>{src}{ext}</trkpt>')
    lines += ['    </trkseg>', '  </trk>', '</gpx>', '']
    Path(path).write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Flightradar24 KML/CSV saved as GPX beside them, by gpsbabel
# --------------------------------------------------------------------------- #
# gpsbabel's xcsv style for Flightradar24's CSV. The quoted "lat,lon" is split
# at its comma, and the human-readable lat/lon parser skips the quote marks.
FR24_CSV_STYLE = """\
DESCRIPTION Flightradar24 CSV
EXTENSION csv
FIELD_DELIMITER COMMA
RECORD_DELIMITER NEWLINE
PROLOGUE Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction
IFIELD TIMET_TIME,"","%ld"
IFIELD IGNORE,"","%s"
IFIELD SHORTNAME,"","%s"
IFIELD LAT_HUMAN_READABLE,"","%s"
IFIELD LON_HUMAN_READABLE,"","%s"
IFIELD ALT_FEET,"","%f"
IFIELD PATH_SPEED_KNOTS,"","%f"
IFIELD PATH_COURSE,"","%f"
"""


def gpsbabel_cmd(gpsbabel, src, out, style):
    """The gpsbabel command making one timed GPX track of a Flightradar24 KML or
    CSV. Their timed points are read as waypoints and become the track; a KML's
    untimed route lines are dropped first. GPX 1.0 keeps the CSV's speed and course."""
    if src.suffix.lower() == ".csv":
        read = ["-i", f"xcsv,style={style}", "-f", str(src)]
    else:
        read = ["-i", "kml", "-f", str(src), "-x", "nuketypes,tracks,routes"]
    return [gpsbabel, *read, "-x", "transform,trk=wpt,del", "-o", "gpx", "-F", str(out)]


def made_by_gpsbabel(path):
    try:
        with open(path, "rb") as f:
            return b'creator="GPSBabel' in f.read(1024)
    except OSError:
        return False


def save_fr24_gpx(tracks, gpsbabel, keep=()):
    """Save each Flightradar24 KML/CSV among tracks as <name>.gpx beside it, from
    the CSV when both are there. A GPX gpsbabel did not make, or a path in keep,
    is never written over; one newer than its source is left alone. Returns the
    lines to print: the GPX is a convenience, so trouble is only a warning."""
    jobs = {}
    for tr in tracks:
        if tr.kind != "fr24" or tr.path.suffix.lower() not in (".kml", ".csv") or len(tr.pts) < 2:
            continue
        out = tr.path.resolve().with_suffix(".gpx")    # one GPX however the file was named
        if out not in jobs or tr.path.suffix.lower() == ".csv":
            jobs[out] = tr.path
    keep = {Path(k).resolve() for k in keep if k}
    todo = []
    for out, src in sorted(jobs.items()):
        if out.resolve() in keep:
            continue
        if out.exists():
            if not made_by_gpsbabel(out):
                todo.append((out, src, "kept"))
                continue
            if out.stat().st_mtime >= src.stat().st_mtime:
                continue
        todo.append((out, src, None))
    lines = [t("gpx_kept", out=out.name, src=src.name) for out, src, why in todo if why]
    todo = [(out, src) for out, src, why in todo if not why]
    if not todo:
        return lines
    with tempfile.TemporaryDirectory() as tmp:
        style = Path(tmp) / "fr24.style"
        style.write_text(FR24_CSV_STYLE, encoding="utf-8")
        for i, (out, src) in enumerate(todo):
            part = out.with_name(f".{out.name}.part")
            try:
                r = subprocess.run(gpsbabel_cmd(gpsbabel, src, part, style),
                                   capture_output=True, text=True)
            except OSError:
                names = ", ".join(s.name for _, s in todo[i:])
                return lines + [t("gpx_no_gpsbabel", gpsbabel=gpsbabel, src=names)]
            n = 0
            if r.returncode == 0 and part.is_file():
                try:
                    n = len(load_track(part).pts)
                except (TrimError, OSError, ET.ParseError, ValueError, TypeError, IndexError):
                    n = 0
            if n < 2:
                err = (r.stderr or r.stdout or "").strip().splitlines()
                part.unlink(missing_ok=True)
                lines.append(t("gpx_failed", src=src.name,
                               err=err[0] if err else f"exit {r.returncode}, {n} points"))
                continue
            try:
                os.replace(part, out)
            except OSError as e:
                part.unlink(missing_ok=True)
                lines.append(t("gpx_failed", src=src.name, err=e))
                continue
            lines.append(t("gpx_saved", src=src.name, out=out.name, n=n))
    return lines


# --------------------------------------------------------------------------- #
# --check: coverage
# --------------------------------------------------------------------------- #
MAX_GAP = 2.0       # s: a hole in the camera's own GPS longer than this is missing data
FILL_GAP = 15.0     # s: a fill source may skip this long between points
SEAM_NEAR = 10.0    # s of camera data beside a seam used to line the fill up with it
SEAM_FAR = 1800.0   # s: altitude can be matched from camera GPS this far away
FAR_POINTS = 100    # camera points used for such a distant altitude match
KIND_RANK = {"skydemon": 0, "other": 1, "fr24": 2}


def cadence(times):
    d = [secs(a, b) for a, b in zip(times, times[1:]) if b > a]
    return statistics.median(d) if d else None


def gap_limit(times, floor):
    c = cadence(times)
    return max(floor, 3 * c) if c else floor


def spans(times, gap):
    """Stretches of time where consecutive points are at most gap seconds apart."""
    out = []
    for x in times:
        if out and secs(out[-1][1], x) <= gap:
            out[-1][1] = x
        else:
            out.append([x, x])
    return [tuple(sp) for sp in out]


def mixed_spans(pts, camera_gap):
    """Like spans(), for a file holding both the camera's points and points
    filled in from other tracks (<src>): a stretch next to a filled point may
    be as long as that source's own spacing allows."""
    by_src = {}
    for p in pts:
        if p.src:
            by_src.setdefault(p.src, []).append(p.t)
    limit = {k: gap_limit(v, FILL_GAP) for k, v in by_src.items()}
    out = []
    for a, b in zip([None] + pts[:-1], pts):
        if a is not None:
            gap = (max(limit.get(a.src, 0.0), limit.get(b.src, 0.0))
                   if a.src or b.src else camera_gap)
            if secs(out[-1][1], b.t) <= gap:
                out[-1][1] = b.t
                continue
        out.append([b.t, b.t])
    return [tuple(sp) for sp in out]


def uncovered(span_list, s, e, longer_than):
    """The parts of [s, e] outside the spans, longer than longer_than seconds."""
    out, cur = [], s
    for a, b in span_list:
        if b < s or a > e:
            continue
        if a > cur:
            out.append((cur, min(a, e)))
        cur = max(cur, b)
    if e > cur:
        out.append((cur, e))
    return [(a, b) for a, b in out if secs(a, b) > longer_than]


def total(intervals):
    return sum(secs(a, b) for a, b in intervals)


def fmt_spans(intervals):
    return ", ".join(f"{a:%H:%M:%S}Z – {b:%H:%M:%S}Z" for a, b in intervals)


def intersect(intervals, span_list):
    out = []
    for a, b in intervals:
        for x, y in span_list:
            lo, hi = max(a, x), min(b, y)
            if hi > lo:
                out.append((lo, hi))
    return out


def subtract(intervals, cut_out):
    out = []
    for a, b in intervals:
        pieces = [(a, b)]
        for x, y in cut_out:
            nxt = []
            for p, q in pieces:
                if y <= p or x >= q:
                    nxt.append((p, q))
                    continue
                if x > p:
                    nxt.append((p, x))
                if y < q:
                    nxt.append((y, q))
            pieces = nxt
        out += pieces
    return [(a, b) for a, b in out if secs(a, b) > 1e-3]


class Source:
    """A track used to fill gaps, with its own coverage."""

    def __init__(self, track):
        self.track, self.pts, self.times = track, track.pts, track.times
        self.name, self.kind = track.path.name, track.kind
        self.spans = spans(self.times, gap_limit(self.times, FILL_GAP))
        self.starts = [a for a, _ in self.spans]

    def covers(self, x):
        i = bisect.bisect_right(self.starts, x) - 1
        return i >= 0 and self.spans[i][0] <= x <= self.spans[i][1]

    def at(self, x):
        return interp(self.pts, self.times, x)


def drop_placeholder(pts, gap):
    """gopro-telemetry starts its GPX with a copy of the first fix, dated to the
    video's first frame. After a long wait for a fix that copy sits far from
    where the camera was. Returns (points, placeholder or None)."""
    if (len(pts) >= 2 and (pts[0].lat, pts[0].lon, pts[0].ele) == (pts[1].lat, pts[1].lon, pts[1].ele)
            and secs(pts[0].t, pts[1].t) > gap):
        return pts[1:], pts[0]
    return pts, None


# --------------------------------------------------------------------------- #
# --check: filling
# --------------------------------------------------------------------------- #
# lat/lon/ele: mean (camera - source) beside the seam; edge: the altitude
# difference at the seam itself, which the fill fades into over SEAM_NEAR
# seconds so the altitude meets without a step. (Positions keep the mean: the
# camera's first points after a fix lag a little, and a few metres don't show.)
Offset = namedtuple("Offset", "t lat lon ele near ref m edge")


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def seam_offset(cam, ref, src, x, side):
    """Mean (camera - source) beside a seam at x: side -1 uses the camera's
    points just before x, +1 just after. Without camera points right there,
    the altitude alone is matched from camera GPS further away (ref)."""
    lo, hi = (x - timedelta(seconds=SEAM_NEAR), x) if side < 0 else (x, x + timedelta(seconds=SEAM_NEAR))
    near = [(c, src.at(c.t)) for c in cam if lo <= c.t <= hi and src.covers(c.t)]
    if near:
        dlat = mean(c.lat - s.lat for c, s in near)
        dlon = mean(c.lon - s.lon for c, s in near)
        lat = math.radians(mean(c.lat for c, _ in near))
        c, s = min(near, key=lambda cs: abs(secs(x, cs[0].t)))
        edge = c.ele - s.ele if c.ele is not None and s.ele is not None else None
        return Offset(c.t, dlat, dlon,
                      mean(c.ele - s.ele for c, s in near if c.ele is not None and s.ele is not None),
                      True, None, math.hypot(dlat * 111320, dlon * 111320 * math.cos(lat)), edge)
    far = [(r, name) for r, name in ref
           if (r.t <= x if side < 0 else r.t >= x) and abs(secs(x, r.t)) <= SEAM_FAR
           and r.ele is not None and src.covers(r.t)]
    if not far:
        return None
    far.sort(key=lambda rn: abs(secs(x, rn[0].t)))
    far = far[:FAR_POINTS]
    dele = mean(r.ele - src.at(r.t).ele for r, _ in far if src.at(r.t).ele is not None)
    if dele is None:
        return None
    when = far[0][0].t
    return Offset(when, None, None, dele, False, far[0][1], None, None)


def blend(left, right, x, comp):
    a = getattr(left, comp) if left else None
    b = getattr(right, comp) if right else None
    if a is None and b is None:
        return 0.0
    if a is None:
        return b
    if b is None:
        return a
    span = secs(left.t, right.t)
    f = 0.0 if span <= 0 else min(max(secs(left.t, x) / span, 0.0), 1.0)
    return a + f * (b - a)


def fill_points(cam, ref, src, lo, hi):
    """The source's points from lo to hi, lined up with the camera at the seams.
    Returns (points, left offset, right offset)."""
    left = seam_offset(cam, ref, src, lo, -1)
    right = seam_offset(cam, ref, src, hi, +1)
    raw = [p for p in src.pts if lo <= p.t <= hi]
    for x in (lo, hi):
        if not any(p.t == x for p in raw):
            raw.append(src.at(x))
    out = []
    for p in sorted(raw, key=lambda q: q.t):
        dlat, dlon, dele = (blend(left, right, p.t, comp) for comp in ("lat", "lon", "ele"))
        for o in (left, right):
            if o is not None and o.edge is not None and o.ele is not None:
                dele += max(0.0, 1.0 - abs(secs(o.t, p.t)) / SEAM_NEAR) * (o.edge - o.ele)
        out.append(Pt(p.t, p.lat + dlat, p.lon + dlon,
                      None if p.ele is None else p.ele + dele, p.spd, p.crs, src.name))
    return out, left, right


def fmt_ft(m):
    return f"{m / FT:+.0f} ft"


def match_text(left, right, src_name):
    sides = [o for o in (left, right) if o is not None]
    if not sides:
        return t("match_none", src=src_name)
    near = [o for o in sides if o.near]
    ele = mean(o.ele for o in sides)
    if near:
        return t("match_full", ele=fmt_ft(ele) if ele is not None else "-",
                 pos=f"{mean(o.m for o in near):.0f}")
    refs = ", ".join(sorted({o.ref or t("ref_self") for o in sides}))
    return t("match_alt", ele=fmt_ft(ele), ref=refs)


# --------------------------------------------------------------------------- #
# --check: one clip
# --------------------------------------------------------------------------- #
class Clip:
    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.name
        self.error = None
        self.missing = []
        self.notes = []
        self.clock = None
        self.moved = None


def gopro_key(path):
    m = CHAPTER_RE.match(Path(path).stem)
    return (int(m.group(3)), int(m.group(2)), Path(path).name) if m else (10 ** 6, 0, Path(path).name)


def camera_points(track):
    """The camera's own points: anything filled in by an earlier run is left out."""
    return [p for p in track.pts if p.src is None]


def find_video(stem, dirs):
    best = None
    for d in dirs:
        try:
            entries = list(Path(d).iterdir())
        except OSError:
            continue
        for f in entries:
            if f.stem.lower() == stem.lower() and f.suffix.lower() in (".360", ".mp4"):
                if best is None or (f.suffix.lower() == ".360" and best.suffix.lower() != ".360"):
                    best = f
        if best:
            return best
    return None


def check_clip(clip, args):
    """Window, camera coverage and missing intervals for one clip (no questions)."""
    try:
        track = load_track(clip.path)
    except (TrimError, OSError, ET.ParseError, ValueError, TypeError, IndexError) as e:
        clip.error = e.text() if isinstance(e, TrimError) else str(e)
        return clip
    clip.track = track
    raw = sorted(camera_points(track), key=lambda p: p.t)
    gap = gap_limit([p.t for p in raw], args.max_gap)
    clip.gap = gap
    clip.camera, placeholder = drop_placeholder(raw, gap)
    video = Path(args.video) if args.video else find_video(
        clip.path.stem, [Path(args.video_dir)] if args.video_dir else [clip.path.parent])
    if video is None:
        dirs = args.video_dir or str(clip.path.parent)
        clip.error = t("no_video", stem=clip.path.stem, dirs=dirs)
        return clip
    clip.video = video
    try:
        v_ct, v_start, v_dur, clip.notes = video_window(args.ffprobe, video)
    except TrimError as e:
        clip.error = bare(t("chk_ffprobe_missing", ffprobe=args.ffprobe)
                          if e.key == "err_ffprobe_missing" else e.text())
        return clip
    if v_start is None or v_dur is None:
        clip.error = t("chk_no_ct" if v_start is None else "chk_no_dur", video=video.name)
        return clip
    start = v_start - timedelta(hours=args.tz)
    # gopro-telemetry dates its first point to the video's first frame in GPS time
    first = raw[0] if raw else None
    if first is not None and "gopro-telemetry" in track.creator.lower():
        clip.clock = secs(start, first.t)
        if abs(clip.clock) >= 1.0 and abs(clip.clock) < 12 * 3600:
            start = first.t
            clip.moved = start
    clip.s, clip.dur = start, v_dur
    clip.e = start + timedelta(seconds=v_dur)
    have = track.pts if not args.refill else clip.camera
    have = [p for p in have if p is not placeholder]
    clip.have = sorted(have, key=lambda p: p.t)
    span_list = mixed_spans(clip.have, gap)
    clip.missing = uncovered(span_list, clip.s, clip.e, gap)
    inside = [p.t for p in clip.have if clip.s <= p.t <= clip.e]
    clip.largest = max((secs(a, b) for a, b in zip(inside, inside[1:])), default=0.0)
    clip.filled_before = {}
    for p, q in zip(clip.have, clip.have[1:]):         # each filled point counts up to the next
        if p.src and clip.s <= p.t < clip.e:
            clip.filled_before[p.src] = clip.filled_before.get(p.src, 0.0) + secs(p.t, min(q.t, clip.e))
    return clip


def status_row(clip, width):
    words = [t(k) for k in ("st_complete", "st_missing", "st_nogps", "st_error")]
    w = max(len(x) for x in words)
    if clip.error:
        return f"  {clip.name:<{width}}  {t('st_error'):<{w}}  {clip.error}"
    clock = t("row_clock", off=f"{clip.clock:+.2f}") if clip.clock is not None else ""
    if not clip.missing:
        extra = "".join(t("row_filled", sec=f"{v:.1f}", src=k) for k, v in clip.filled_before.items())
        return (f"  {clip.name:<{width}}  {t('st_complete'):<{w}}  "
                + t("row_complete", dur=fmt_secs(clip.dur), gap=f"{clip.largest:.1f}") + extra + clock)
    if not clip.have or total(clip.missing) >= clip.dur - clip.gap:
        return f"  {clip.name:<{width}}  {t('st_nogps'):<{w}}  " + t("row_nogps", dur=fmt_secs(clip.dur))
    return (f"  {clip.name:<{width}}  {t('st_missing'):<{w}}  "
            + t("row_missing", miss=f"{total(clip.missing):.1f}", dur=fmt_secs(clip.dur),
                spans=fmt_spans(clip.missing)) + clock)


# --------------------------------------------------------------------------- #
# --check: sources, questions, writing
# --------------------------------------------------------------------------- #
class Sources:
    """Fill sources: given with --fill, and found next to the clips."""

    def __init__(self, args, folders):
        self.args, self.cache, self.found = args, {}, None
        self.folders = folders

    def load(self, path):
        path = Path(path)
        key = str(path.resolve())
        if key not in self.cache:
            try:
                self.cache[key] = Source(load_track(path))
            except (TrimError, OSError, ET.ParseError, ValueError, TypeError, IndexError) as e:
                self.cache[key] = e
        return self.cache[key]

    def discovered(self):
        if self.found is None:
            seen, found = set(), []
            for d in self.folders + [Path(x) for x in self.args.search]:
                for f in sorted(Path(d).iterdir()) if Path(d).is_dir() else []:
                    if (f.suffix.lower() not in (".gpx", ".kml", ".csv")
                            or CLIP_PREFIX_RE.match(f.name) or not f.is_file()):
                        continue
                    src = self.load(f)
                    if isinstance(src, Exception) or src.kind not in KIND_RANK or len(src.pts) < 2:
                        continue
                    # gpsbabel's copy of a Flightradar24 KML/CSV beside it: offer the original
                    if (f.suffix.lower() == ".gpx" and src.track.creator.startswith("GPSBabel")
                            and any(f.with_suffix(x).is_file()
                                    for x in (".kml", ".csv", ".KML", ".CSV"))):
                        continue
                    # the same flight as KML, CSV and gpsbabel GPX: offer it once
                    key = (src.kind, src.times[0], src.times[-1], len(src.pts))
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(src)
            self.found = found
        return self.found

    def flightradar24(self):
        """Every Flightradar24 track this run has seen: beside the clips, in
        --search, given with --fill or typed at a prompt."""
        for d in self.folders + [Path(x) for x in self.args.search]:
            for f in sorted(Path(d).iterdir()) if Path(d).is_dir() else []:
                if (f.suffix.lower() in (".kml", ".csv") and f.is_file()
                        and not CLIP_PREFIX_RE.match(f.name)):
                    self.load(f)
        for f in self.args.fill:
            self.load(user_path(f))
        return [s.track for s in self.cache.values()
                if not isinstance(s, Exception) and s.kind == "fr24"]

    def ranked(self, missing, used):
        out = []
        for src in self.discovered():
            if src.name in used:
                continue
            cov = total(intersect(missing, src.spans))
            if cov > 0:
                out.append((KIND_RANK[src.kind], -cov, src.name, src, cov))
        return [(src, cov) for *_, src, cov in sorted(out, key=lambda x: x[:3])]


def user_path(text):
    text = text.strip().strip('"').strip("'")
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", text)
    if m and os.name != "nt":
        p = Path(f"/mnt/{m.group(1).lower()}") / m.group(2).replace("\\", "/")
        if p.exists():
            return p
    return Path(os.path.expanduser(text))


def ask(prompt):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not sys.stdin.isatty():
        print(line.strip())               # answers from a pipe: show them, end the line
    if not line:
        return None
    return line.strip()


def kind_label(kind):
    return t("kind_" + kind) if "kind_" + kind in MESSAGES["en"] else kind


def apply_source(clip, src, ref, fills, missing):
    """Fill what src covers of the missing intervals; returns the rest."""
    got = intersect(missing, src.spans)
    if not got:
        print(t("fill_nothing", name=src.name))
        return missing
    n = 0
    lefts, rights = [], []
    taken = {p.t for p in clip.have}
    for lo, hi in got:
        pts, left, right = fill_points(clip.camera, ref, src, lo, hi)
        fills.extend(pts)
        n += sum(1 for p in pts if p.t not in taken)
        lefts.append(left)
        rights.append(right)
    left = next((o for o in lefts if o), None)
    right = next((o for o in reversed(rights) if o), None)
    print(t("fill_done", sec=f"{total(got):.1f}", src=src.name, n=n,
            match=match_text(left, right, src.name)))
    rest = subtract(missing, got)
    if rest:
        print(t("still_missing", spans=fmt_spans(rest), sec=f"{total(rest):.1f}"))
    return rest


def fill_clip(clip, args, sources, ref, interactive):
    missing, fills, used = list(clip.missing), [], set()
    print(t("gap_head", name=clip.name, spans=fmt_spans(missing),
            miss=f"{total(missing):.1f}", dur=fmt_secs(clip.dur)))
    for f in args.fill:
        if not missing:
            break
        src = sources.load(user_path(f))
        if isinstance(src, Exception):
            print(t("fill_bad", name=f, err=src.text() if isinstance(src, TrimError) else src))
            continue
        used.add(src.name)
        missing = apply_source(clip, src, ref, fills, missing)
    while missing and (interactive or args.yes):
        offers = sources.ranked(missing, used)
        if args.yes:
            if not offers:
                break
            src = offers[0][0]
        else:
            if offers:
                print(t("cand_head"))
                wn = max(len(s.name) for s, _ in offers)
                wk = max(len(kind_label(s.kind)) for s, _ in offers)
                for i, (s, cov) in enumerate(offers, 1):
                    print(t("cand_row", i=i, name=f"{s.name:<{wn}}", kind=f"{kind_label(s.kind):<{wk}}",
                            cov=f"{cov:.1f}", miss=f"{total(missing):.1f}"))
                answer = ask(t("ask_choose", n=len(offers)))
            else:
                answer = ask(t("ask_file"))
            if answer is None or answer.lower() in ("n", "no", "nej", "s", "skip", "q"):
                break
            if answer == "" and offers:
                src = offers[0][0]
            elif answer == "":
                break
            elif answer.isdigit() and 1 <= int(answer) <= len(offers):
                src = offers[int(answer) - 1][0]
            else:
                src = sources.load(user_path(answer))
                if isinstance(src, Exception):
                    print(t("fill_bad", name=answer, err=src.text() if isinstance(src, TrimError) else src))
                    continue
        used.add(src.name)
        missing = apply_source(clip, src, ref, fills, missing)
    if not fills:
        print(t("left_as_is"))
        return missing
    merged = {p.t: p for p in fills}
    merged.update({p.t: p for p in clip.have})        # the camera's points (and earlier fills) win
    pts = sorted(merged.values(), key=lambda p: p.t)
    times = [p.t for p in pts]
    s, e = max(clip.s, times[0]), min(clip.e, times[-1])
    out = cut(pts, times, s, e)
    n_cam = sum(1 for p in out if p.src is None)
    if args.output:
        write_gpx(args.output, out, Path(args.output).stem)
        print(t("updated_to", n=len(out), cam=n_cam, fill=len(out) - n_cam, out=args.output))
    else:
        orig = clip.path.with_name(clip.path.name + ".orig")
        if clip.track.kind != "trim":
            shutil.copy2(clip.path, orig)
        write_gpx(clip.path, out, clip.path.stem)
        print(t("updated", name=clip.name, cam=n_cam, fill=len(out) - n_cam, orig=orig.name))
    return missing


def check_main(args, ap):
    for opt, val in (("--start", args.start), ("--duration", args.duration)):
        if val:
            ap.error(t("err_check_trim", opt=opt))
    if args.hz:
        ap.error(t("err_check_trim", opt="--hz"))
    paths = [Path(p) for p in (args.paths or ["."])]
    clips = []
    for p in paths:
        if p.is_dir():
            clips += [Clip(f) for f in sorted(p.iterdir(), key=gopro_key)
                      if CAMERA_GPX_RE.match(f.name) and f.is_file()]
        else:
            clips.append(Clip(p))
    if not clips:
        die("err_no_clips", where=", ".join(str(p) for p in paths))
    for opt, val in (("--video", args.video), ("--output", args.output)):
        if val and len(clips) > 1:
            ap.error(t("err_check_one", opt=opt))

    print(t("check_head", n=len(clips),
            where=t("check_where", dir=args.video_dir) if args.video_dir else ""))
    for clip in clips:
        check_clip(clip, args)
    width = max(len(c.name) for c in clips)
    for clip in clips:
        print(status_row(clip, width))
    for clip in clips:
        for key, kw in clip.notes:
            print(t(key, **kw))
        if clip.moved:
            print(t("clock_moved", name=clip.name, off=f"{clip.clock:+.1f}",
                    start=f"{clip.moved:%Y-%m-%d %H:%M:%S}"))
        video = getattr(clip, "video", None)
        if video is not None and not args.video and video.suffix.lower() != ".360":
            print(t("mp4_video", name=clip.name, video=video.name))

    todo = [c for c in clips if not c.error and c.missing]
    folders = sorted({c.path.parent.resolve() for c in clips}, key=str)
    sources = Sources(args, folders)
    if todo and args.dry_run:
        print(t("dry_run"))
    elif todo:
        # camera GPS from every clip next to these, for matching the altitude
        ref = []
        for d in folders:
            for f in sorted(d.iterdir(), key=gopro_key):
                if CAMERA_GPX_RE.match(f.name) and f.is_file():
                    try:
                        tr = load_track(f)
                    except (TrimError, OSError, ET.ParseError, ValueError, TypeError, IndexError):
                        continue
                    pts, _ = drop_placeholder(camera_points(tr), gap_limit(tr.times, args.max_gap))
                    ref += [(p, f.name) for p in pts if p.ele is not None]
        interactive = args.ask if args.ask is not None else sys.stdin.isatty()
        for clip in todo:
            clip.missing = fill_clip(clip, args, sources, ref, interactive and not args.yes)

    # Flightradar24's KML/CSV also as GPX, whether or not anything was filled
    if not args.dry_run:
        lines = save_fr24_gpx(sources.flightradar24(), args.gpsbabel, keep=[args.output])
        if lines:
            print("\n" + "\n".join(lines))

    left = sum(1 for c in clips if not c.error and c.missing)
    errors = sum(1 for c in clips if c.error)
    print(t("sum_left", k=left, n=len(clips)) if left else t("sum_ok", n=len(clips) - errors))
    if errors:
        print(t("sum_err", k=errors))
    sys.exit(1 if errors else 3 if left else 0)


# --------------------------------------------------------------------------- #
# cutting a track (the original job)
# --------------------------------------------------------------------------- #
def trim_main(args, ap):
    if len(args.paths) != 2:
        ap.error(t("usage_trim"))
    track_in, track_out = args.paths
    if not args.video and not (args.start and args.duration):
        ap.error(t("err_args"))
    if args.hz < 0:
        ap.error(t("err_hz"))

    try:
        track = load_track(track_in)
    except TrimError as e:
        die("err_read", path=track_in, err=e.text())
    except (OSError, ET.ParseError, ValueError, TypeError, IndexError) as e:
        die("err_read", path=track_in, err=e)
    pts = track.pts
    if len(pts) < 2:
        die("err_points", path=track_in)
    times = [p.t for p in pts]
    first, last = times[0], times[-1]
    print(t("source", n=len(pts), first=f"{first:%Y-%m-%d %H:%M:%S}", last=f"{last:%H:%M:%S}"))
    # a Flightradar24 KML/CSV is also saved as GPX beside it (never over OUTPUT)
    for line in save_fr24_gpx([track], args.gpsbabel, keep=[track_out]):
        print(line)

    v_start = v_dur = None
    if args.video:
        try:
            v_ct, v_start, v_dur, notes = video_window(args.ffprobe, args.video)
        except TrimError as e:
            sys.stdout.flush()
            print(e.text(), file=sys.stderr)
            sys.exit(1)
        print(t("video", name=Path(args.video).name,
                ct=fmt_time(v_ct) if v_ct else "-",
                dur=fmt_secs(v_dur) if v_dur is not None else "-"))
        for key, kw in (notes if not args.start else []):
            print(t(key, **kw))
        if not args.start and v_start is None:
            die("err_no_ct", path=args.video)
        if not args.duration and v_dur is None:
            die("err_no_dur", path=args.video)

    try:
        dur = timedelta(seconds=parse_duration(args.duration) if args.duration else v_dur)
    except ValueError as e:
        ap.error(f"--duration: {e}")
    if dur <= timedelta(0):
        ap.error(t("err_duration"))

    # the start is either a time of day (date taken from the track) or a moment
    tod = None
    if args.start:
        m = TIME_RE.match(args.start.strip())
        if m:
            h, mi, sec = m.groups()
            tod = int(h) * 3600 + int(mi) * 60 + float(sec)
        else:
            try:
                v_start = parse_dt(args.start)
            except TrimError as e:
                die("err_start", err=e.text())

    def window_start(tz):
        if tod is not None:
            base = (first.replace(hour=0, minute=0, second=0, microsecond=0)
                    + timedelta(seconds=tod) - timedelta(hours=tz))
            # same day as the track, else the next/previous one (flight over midnight)
            cands = [base + timedelta(days=k) for k in (0, 1, -1)]
            return next((c for c in cands if c <= last and c + dur >= first), base)
        return v_start - timedelta(hours=tz)

    def tz_hints():
        """Lines suggesting the --tz (0, 1, 2) that puts the window fully inside the track."""
        out = []
        for tz in (0, 1, 2):
            if tz == args.tz:
                continue
            s = window_start(tz)
            if first <= s and s + dur <= last:
                how = t("tz_without") if tz == 0 else t("tz_with", tz=tz)
                out.append(t("tz_fits", how=how, a=f"{s:%H:%M:%S}", b=f"{s + dur:%H:%M:%S}"))
        return out

    start = window_start(args.tz)
    end = start + dur
    print(t("window", start=f"{start:%Y-%m-%d %H:%M:%S}", end=f"{end:%H:%M:%S}",
            dur=f"{dur.total_seconds():g}"))

    if end < first or start > last:
        sys.stdout.flush()
        print(t("outside"), file=sys.stderr)
        print("\n".join(tz_hints() or [t("tz_none")]), file=sys.stderr)
        sys.exit(2)

    s, e = max(start, first), min(end, last)
    if (s, e) != (start, end):
        print(t("partial", a=f"{s:%H:%M:%S}", b=f"{e:%H:%M:%S}"))
        for line in tz_hints():
            print(line)

    out = cut(pts, times, s, e, args.hz)

    # summary, to check against the video
    n_src = sum(1 for x in times if s <= x <= e)
    i0 = max(bisect.bisect_right(times, s) - 1, 0)
    i1 = min(bisect.bisect_left(times, e), len(pts) - 1)
    gap = max(((times[i + 1] - times[i]).total_seconds() for i in range(i0, i1)), default=0)
    print(t("in_window", n=n_src, gap=f"{gap:g}"))
    eles = [p.ele for p in out if p.ele is not None]
    if eles:
        print(t("altitude", lo=min(eles), hi=max(eles),
                lo_ft=min(eles) / FT, hi_ft=max(eles) / FT))
    spds = [p.spd / KT for p in out if p.spd is not None]
    if spds:
        print(t("speed_measured", lo=min(spds), hi=max(spds)))
    else:
        kts = [dist_m(a, b) / (b.t - a.t).total_seconds() / KT
               for a, b in zip(out, out[1:]) if b.t > a.t]
        if kts:
            print(t("speed_derived", lo=min(kts), hi=max(kts)))
    if out[0].crs is not None and out[-1].crs is not None:
        print(t("course", a=out[0].crs, b=out[-1].crs))

    write_gpx(track_out, out, Path(track_out).stem)
    print(t("saved", n=len(out), out=track_out))


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    global LANG
    # a redirected stdout on Windows may not be UTF-8: replace, don't crash
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(
        usage="%(prog)s TRACK OUTPUT (--video CLIP | --start TIME --duration LEN) [options]\n"
              "       %(prog)s --check [CAMERA.gpx | FOLDER ...] [options]",
        description="Fit GPS tracks to GoPro clips. Cut a track (e.g. a Flightradar24 export)\n"
                    "down to exactly one clip - or, with --check, check the GPX extracted from\n"
                    "each clip against the clip and fill what is missing from another track,\n"
                    "keeping the camera's own points.",
        epilog="examples:\n"
               "  trim_gpx.py fl03.kml GS010132.gpx --video /mnt/e/DCIM/100GOPRO/GS010132.360\n"
               "  trim_gpx.py fl03.csv GS010132.gpx --start 2026-10-17T12:05:07Z --duration 62.208\n"
               "  trim_gpx.py --check . --video-dir /mnt/e/DCIM/100GOPRO\n"
               "  trim_gpx.py --check GS010130.gpx --fill SD_ESTT-ESTL.gpx --fill fl02_42294bf5.kml\n"
               "\nSee MANUAL.md for the whole pipeline (camera GPS / SkyDemon / Flightradar24 -> OVRLEY).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", metavar="PATH",
                    help="cutting: TRACK and OUTPUT. --check: camera GPX files or folders "
                         "(default: this folder)")
    ap.add_argument("--video", metavar="FILE",
                    help="the clip's original file, e.g. GS010132.360: start and length from "
                         "its creation_time and duration (ffprobe)")
    ap.add_argument("--start",
                    help="clip start: HH:MM:SS, ISO time or exiftool format "
                         "(2026:10:17 12:05:07); without a date the track's date is used. "
                         "Overrides --video")
    ap.add_argument("--duration",
                    help="clip length in seconds (62.208) or M:SS (1:02). Overrides --video")
    ap.add_argument("--tz", type=float, default=0.0,
                    help="the start time is the camera's local clock, with this UTC offset in "
                         "hours (2 = CEST, 1 = CET). Default 0: the camera runs on UTC. If the "
                         "window misses the track, the offset that fits is suggested")
    ap.add_argument("--hz", type=float, default=0.0, metavar="N",
                    help="resample to N points per second (default: keep the source points; "
                         "OVRLEY interpolates between them itself and does not need this)")
    chk = ap.add_argument_group("checking camera GPX (--check)")
    chk.add_argument("--check", action="store_true",
                     help="check each camera GPX against its clip and fill what is missing")
    chk.add_argument("--video-dir", metavar="DIR",
                     help="where the clips' .360 (or .mp4) files are (default: next to the GPX)")
    chk.add_argument("--fill", action="append", default=[], metavar="TRACK",
                     help="fill from this track first (repeatable, in order of preference)")
    chk.add_argument("--search", action="append", default=[], metavar="DIR",
                     help="also look for SkyDemon/Flightradar24 tracks here (repeatable)")
    chk.add_argument("-y", "--yes", action="store_true",
                     help="fill from the best track found without asking")
    chk.add_argument("--ask", action=argparse.BooleanOptionalAction, default=None,
                     help="ask before filling (default: when run in a terminal)")
    chk.add_argument("--dry-run", action="store_true", help="only report, change nothing")
    chk.add_argument("--refill", action="store_true",
                     help="redo gaps filled by an earlier run (the camera's points are kept)")
    chk.add_argument("-o", "--output", metavar="GPX",
                     help="write here instead of updating the camera GPX (one clip)")
    chk.add_argument("--max-gap", type=float, default=MAX_GAP, metavar="S",
                     help=f"a hole in the camera's GPS longer than this is missing data "
                          f"(default: {MAX_GAP:g} s)")
    ap.add_argument("--ffprobe", default="ffprobe", help="ffprobe to use (default: ffprobe)")
    ap.add_argument("--gpsbabel", default="gpsbabel",
                    help="gpsbabel to use when saving Flightradar24 KML/CSV as GPX beside them "
                         "(default: gpsbabel)")
    ap.add_argument("--lang", choices=["en", "sv"], default=default_lang(),
                    help="message language (default: $GOPRO_LANG or en)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()
    LANG = args.lang
    if args.check:
        check_main(args, ap)
    else:
        for opt, val in (("--video-dir", args.video_dir), ("--fill", args.fill),
                         ("--search", args.search), ("--yes", args.yes), ("--ask", args.ask),
                         ("--dry-run", args.dry_run), ("--refill", args.refill),
                         ("--output", args.output), ("--max-gap", args.max_gap != MAX_GAP)):
            if val:
                ap.error(t("err_needs_check", opt=opt))
        trim_main(args, ap)


if __name__ == "__main__":
    main()
