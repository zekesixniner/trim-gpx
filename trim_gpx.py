#!/usr/bin/env python3
"""
trim_gpx.py - cut a time window out of a GPX, KML or CSV track so that it
matches one video clip.

Built to rebuild the GPS telemetry of a GoPro clip recorded without a
satellite fix from Flightradar24 flight data, ready for OVRLEY. See README.md
and MANUAL.md.

Reads every timestamped point: <trkpt>, <wpt> and <rtept> in GPX 1.0/1.1
(also gpsbabel output, where the timed points are <wpt>), Placemark/TimeStamp
and gx:Track in KML, and Flightradar24's CSV export. The first and last point
are interpolated so that the track starts and ends exactly on the clip.

Measured speed and course come along when the source has them (Flightradar24
KML and CSV, <speed>/<course> in GPX) and are written to every point as a
Garmin TrackPointExtension (speed in m/s, course in degrees). OVRLEY then uses
that speed instead of deriving it from the positions, which would jump about:
Flightradar24 timestamps are whole seconds.

Run with --help for the options.
Svenska utskrifter: --lang sv, eller GOPRO_LANG=sv.
"""
import argparse
import bisect
import csv
import json
import math
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

__version__ = "1.0.0"

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
# spd = speed in m/s, crs = course in degrees; None when the source has none
Pt = namedtuple("Pt", "t lat lon ele spd crs", defaults=(None, None))

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
    pts = []
    for el in root.iter():
        name = local(el.tag)
        if name in ("trkpt", "wpt", "rtept"):            # GPX
            tm = kid(el, "time")
            if tm is None or not (tm.text or "").strip():
                continue
            ele = kid(el, "ele")
            # GPX 1.0 has <speed>/<course> directly, GPX 1.1 in <extensions>;
            # gpsbabel output of a Flightradar24 KML has them only as text
            spd = number(descendant(el, "speed"))
            crs = number(descendant(el, "course", "heading"))
            if spd is None or crs is None:
                d_spd, d_crs = text_speed_course(kid(el, "desc"), kid(el, "cmt"))
                spd = d_spd if spd is None else spd
                crs = d_crs if crs is None else crs
            pts.append(Pt(parse_dt(tm.text), float(el.get("lat")), float(el.get("lon")),
                          float(ele.text) if ele is not None and ele.text else None,
                          spd, crs))
        elif name == "Placemark":                         # KML, one point per Placemark
            ts = next((e for e in el.iter() if local(e.tag) == "TimeStamp"), None)
            pt = next((e for e in el.iter() if local(e.tag) == "Point"), None)
            when = kid(ts, "when") if ts is not None else None
            coords = kid(pt, "coordinates") if pt is not None else None
            if when is None or coords is None:
                continue
            c = coords.text.strip().split(",")
            pts.append(Pt(parse_dt(when.text), float(c[1]), float(c[0]),
                          float(c[2]) if len(c) > 2 else None, *kml_speed_course(el)))
        elif name == "Track":                             # KML gx:Track
            for w, c in zip(kids(el, "when"), kids(el, "coord")):
                v = c.text.split()
                pts.append(Pt(parse_dt(w.text), float(v[1]), float(v[0]),
                              float(v[2]) if len(v) > 2 else None))
    return pts


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


def read_points(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        pts = read_csv(path)
    else:
        try:
            pts = read_xml(ET.parse(path).getroot())
        except ET.ParseError:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                first_line = f.readline()
            if "," not in first_line:
                raise
            pts = read_csv(path)
    pts.sort(key=lambda p: p.t)
    uniq = []
    for p in pts:
        if not uniq or p.t != uniq[-1].t:
            uniq.append(p)
    return uniq


# --------------------------------------------------------------------------- #
# the clip: ffprobe and GoPro chapters
# --------------------------------------------------------------------------- #
def probe(ffprobe, path):
    """(creation_time as UTC datetime or None, duration in s or None)."""
    cmd = [ffprobe, "-v", "error", "-show_entries",
           "format=duration:format_tags=creation_time", "-of", "json", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        die("err_ffprobe_missing", ffprobe=ffprobe)
    if r.returncode != 0:
        lines = (r.stderr or "").strip().splitlines()
        die("err_ffprobe", path=path, err=lines[-1] if lines else f"exit {r.returncode}")
    fmt = json.loads(r.stdout or "{}").get("format", {})
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    ct, dur = tags.get("creation_time"), fmt.get("duration")
    try:
        return (parse_dt(ct) if ct else None), (float(dur) if dur not in (None, "N/A") else None)
    except TrimError as e:
        die("err_ffprobe", path=path, err=e.text())


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
              lerp(a.ele, b.ele, f), lerp(a.spd, b.spd, f), lerp_deg(a.crs, b.crs, f))


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
        ext = ""
        if p.spd is not None or p.crs is not None:
            ext = ("<extensions><gpxtpx:TrackPointExtension>"
                   + (f"<gpxtpx:speed>{p.spd:.2f}</gpxtpx:speed>" if p.spd is not None else "")
                   + (f"<gpxtpx:course>{p.crs % 360:.1f}</gpxtpx:course>" if p.crs is not None else "")
                   + "</gpxtpx:TrackPointExtension></extensions>")
        lines.append(f'      <trkpt lat="{p.lat:.7f}" lon="{p.lon:.7f}">{ele}'
                     f'<time>{fmt_time(p.t)}</time>{ext}</trkpt>')
    lines += ['    </trkseg>', '  </trk>', '</gpx>', '']
    Path(path).write_text("\n".join(lines), encoding="utf-8")


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
        description="Cut a time window out of a GPX, KML or CSV track (e.g. a Flightradar24\n"
                    "export) so that it matches one video clip - for clips the camera\n"
                    "recorded without GPS.",
        epilog="examples:\n"
               "  trim_gpx.py fl03.kml GS010132.gpx --video /mnt/e/DCIM/100GOPRO/GS010132.360\n"
               "  trim_gpx.py fl03.csv GS010132.gpx --start 2026-10-17T12:05:07Z --duration 62.208\n"
               "  trim_gpx.py fl03.kml GS010132.gpx --start 14:05:07 --duration 1:02 --tz 2\n"
               "\nSee MANUAL.md for the whole pipeline (Flightradar24 -> trim_gpx.py -> OVRLEY).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="track to cut: Flightradar24 KML or CSV, or any GPX/KML")
    ap.add_argument("output", help="GPX file to write")
    ap.add_argument("--video", metavar="FILE",
                    help="take --start and --duration from this clip's creation_time and "
                         "length (ffprobe); use the camera's original file, e.g. GS010132.360")
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
    ap.add_argument("--hz", type=float, default=0.0,
                    help="resample to N points per second (default: keep the source points)")
    ap.add_argument("--ffprobe", default="ffprobe", help="ffprobe for --video (default: ffprobe)")
    ap.add_argument("--lang", choices=["en", "sv"], default=default_lang(),
                    help="message language (default: $GOPRO_LANG or en)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()
    LANG = args.lang
    if not args.video and not (args.start and args.duration):
        ap.error(t("err_args"))
    if args.hz < 0:
        ap.error(t("err_hz"))

    try:
        pts = read_points(args.input)
    except TrimError as e:
        die("err_read", path=args.input, err=e.text())
    except (OSError, ET.ParseError, ValueError, TypeError, IndexError) as e:
        die("err_read", path=args.input, err=e)
    if len(pts) < 2:
        die("err_points", path=args.input)
    times = [p.t for p in pts]
    first, last = times[0], times[-1]
    print(t("source", n=len(pts), first=f"{first:%Y-%m-%d %H:%M:%S}", last=f"{last:%H:%M:%S}"))

    v_start = v_dur = None
    if args.video:
        v_ct, v_start, v_dur, notes = video_window(args.ffprobe, args.video)
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

    if args.hz > 0:
        step = 1.0 / args.hz
        n = int(math.floor((e - s).total_seconds() / step + 1e-9))
        ts = [s + timedelta(seconds=k * step) for k in range(n + 1)]
        if (e - ts[-1]).total_seconds() > 1e-3:
            ts.append(e)
        out = [interp(pts, times, x) for x in ts]
    else:
        out = ([interp(pts, times, s)]
               + [p for p in pts if s < p.t < e]
               + [interp(pts, times, e)])

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

    write_gpx(args.output, out, Path(args.output).stem)
    print(t("saved", n=len(out), out=args.output))


if __name__ == "__main__":
    main()
