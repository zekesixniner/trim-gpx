#!/usr/bin/env python3
"""Tests for trim_gpx.py --check - standard library only: no network, no ffmpeg.

Run from the repository root:

    python3 -m unittest discover -s tests -v

A synthetic flight (see test_trim_gpx.py) is "flown" by a camera that writes
gopro-telemetry-style GPX at 10 Hz, with GPS altitude 190 ft above the
Flightradar24-style barometric altitude, and by a SkyDemon-style logger. Each
test copies the files it needs into its own folder, since --check updates
camera GPX files in place.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import trim_gpx as T                                                     # noqa: E402
from test_trim_gpx import (STUB_FFPROBE, STUB_GPSBABEL, T0,              # noqa: E402
                           synthetic_flight, write_fr24_kml, write_fr24_csv)

SCRIPT = Path(__file__).resolve().parent.parent / "trim_gpx.py"
CAM_FT = 190          # camera GPS altitude above Flightradar24's barometric one
SKY_FT = 185          # SkyDemon's GPS altitude above it


def at(sec):
    return T0 + timedelta(seconds=sec)


def write_camera(path, track, start, dur, holes=(), placeholder=True, empty=False):
    """gopro-telemetry-style GPX for a clip from start (s after T0), dur long,
    with no points inside holes [(from, to), ...] (s after T0)."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" '
           'creator="https://github.com/juanirache/gopro-telemetry">',
           '    <trk>', '        <name>undefined</name>', '        <src>MAX2</src>',
           '        <trkseg>']
    if not empty:
        xs = [start + k / 10 for k in range(int(round(dur * 10)) + 1)]
        xs = [x for x in xs if not any(a < x < b for a, b in holes)]
        if placeholder:
            xs = [start + 0.03] + xs if xs[0] > start + 0.5 else [start + 0.03] + xs[1:]
        for k, x in enumerate(xs):
            src_x = xs[1] if placeholder and k == 0 and xs[1] - xs[0] > 0.5 else x
            p = T.interp(track.pts, track.times, at(src_x))
            ele = p.ele + CAM_FT * T.FT + 0.5 * math.sin(src_x)
            out.append(f'          <trkpt lat="{p.lat}" lon="{p.lon}"><ele>{ele:.4f}</ele>'
                       f'<time>{T.fmt_time(at(x))}</time><fix>3</fix><hdop>2.0</hdop></trkpt>')
    out += ['        </trkseg>', '  </trk>', '</gpx>', '']
    Path(path).write_text("\n".join(out), encoding="utf-8")


def write_skydemon(path, track, start, end):
    """SkyDemon-style log: <ele>, <speed> (m/s) and <time>, a point every 5 s."""
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<gpx version="1.1" creator="SkyDemon Plan v4.3.3.0" xmlns="http://www.topografix.com/GPX/1/1">',
           '  <trk>', '    <name>Test route</name>', '    <trkseg>']
    x = start
    while x <= end:
        p = T.interp(track.pts, track.times, at(x))
        out.append(f'      <trkpt lat="{p.lat:.6f}" lon="{p.lon:.6f}"><ele>{p.ele + SKY_FT * T.FT:.4f}</ele>'
                   f'<speed>{p.spd:.6f}</speed><time>{at(x):%Y-%m-%dT%H:%M:%SZ}</time></trkpt>')
        x += 5
    out += ['    </trkseg>', '  </trk>', '</gpx>', '']
    Path(path).write_text("\n".join(out), encoding="utf-8")


# the clips: start and length in s after T0, and what the camera missed
CLIPS = {
    "GS010001": (100, 60, dict()),                                  # complete
    "GS010002": (200, 60, dict(holes=[(200, 230)])),                # waited 30 s for a fix
    "GS010003": (300, 80, dict(holes=[(330, 350)])),                # dropout in the middle
    "GS010004": (400, 50, dict(empty=True)),                        # no fix at all
    "GS010005": (500, 60, dict(holes=[(540, 561)])),                # lost the fix at the end
}


class CheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.lib = Path(cls.tmp.name) / "lib"
        cls.lib.mkdir()
        rows = synthetic_flight()
        write_fr24_kml(cls.lib / "fl01_aaaa0001.kml", rows)
        write_fr24_csv(cls.lib / "aaaa0001.csv", rows)
        cls.fr = T.load_track(cls.lib / "fl01_aaaa0001.kml")
        write_skydemon(cls.lib / "SD_TEST.gpx", cls.fr, 190, 300)
        db = {}
        for name, (start, dur, kw) in CLIPS.items():
            write_camera(cls.lib / f"{name}.gpx", cls.fr, start, dur, **kw)
            db[f"{name}.360"] = [T.fmt_time(at(start)).replace("Z", ".000000Z"), float(dur)]
        (cls.lib / "db.json").write_text(json.dumps(db))
        for name, text in (("ffprobe_stub", STUB_FFPROBE), ("gpsbabel_stub", STUB_GPSBABEL)):
            (cls.lib / name).write_text(text)
            (cls.lib / name).chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def folder(self, *names):
        """A fresh flight folder holding the named files, plus a card folder with the videos."""
        d = Path(tempfile.mkdtemp(dir=self.tmp.name))
        (d / "card").mkdir()
        for n in CLIPS:
            (d / "card" / f"{n}.360").write_bytes(b"")
        for n in names:
            shutil.copy(self.lib / n, d / n)
        return d

    def run_check(self, d, *args, answers=None, lang="en", env=None):
        """--check in folder d, with the stubs (the stub gpsbabel notes its calls
        in d/gpsbabel.log) unless the test gives --gpsbabel."""
        e = dict(os.environ, GOPRO_LANG=lang, STUB_FFPROBE_DB=str(self.lib / "db.json"),
                 STUB_GPSBABEL_LOG=str(d / "gpsbabel.log"))
        e.update(env or {})
        cmd = [sys.executable, str(SCRIPT), "--check",
               "--gpsbabel", str(self.lib / "gpsbabel_stub"), *map(str, args),
               "--video-dir", str(d / "card"), "--ffprobe", str(self.lib / "ffprobe_stub")]
        if answers is not None:
            cmd.append("--ask")
        return subprocess.run(cmd, capture_output=True, text=True, cwd=d, env=e,
                              input=answers if answers is not None else "")

    def babel_calls(self, d):
        log = d / "gpsbabel.log"
        return log.read_text().splitlines() if log.exists() else []

    def pts(self, path):
        return T.load_track(path).pts

    def assertSmoothSeam(self, pts, max_ft=8, max_kt_jump=25):
        """Where filled and camera points meet: the altitude changes as much as
        the flight itself does over that time (no step), and no speed spike."""
        for a, b, c in zip(pts, pts[1:], pts[2:]):
            if (a.src is None) != (b.src is None):
                fa = T.interp(self.fr.pts, self.fr.times, a.t)
                fb = T.interp(self.fr.pts, self.fr.times, b.t)
                step = (b.ele - a.ele) - (fb.ele - fa.ele)
                self.assertLess(abs(step) / T.FT, max_ft, (a, b))
                v1 = T.dist_m(a, b) / T.secs(a.t, b.t) / T.KT
                v2 = T.dist_m(b, c) / T.secs(b.t, c.t) / T.KT
                self.assertLess(abs(v1 - v2), max_kt_jump, (a, b, c, v1, v2))

    # -- reporting ---------------------------------------------------------------
    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_complete_clip_is_left_alone(self):
        d = self.folder("GS010001.gpx", "fl01_aaaa0001.kml")
        before = (d / "GS010001.gpx").read_bytes()
        r = self.run_check(d, "GS010001.gpx", answers="")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GS010001.gpx  complete", r.stdout)
        self.assertIn("camera clock +0.03 s", r.stdout)
        self.assertEqual((d / "GS010001.gpx").read_bytes(), before)
        self.assertFalse((d / "GS010001.gpx.orig").exists())

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_dry_run_reports_every_clip_and_changes_nothing(self):
        names = [f"{n}.gpx" for n in CLIPS]
        d = self.folder(*names, "fl01_aaaa0001.kml")
        before = {n: (d / n).read_bytes() for n in names}
        r = self.run_check(d, ".", "--dry-run", "--yes")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("GS010001.gpx  complete", out)
        self.assertIn("GS010002.gpx  missing   30.0 s of 60 s: 11:03:20Z – 11:03:50Z", out)
        self.assertIn("GS010003.gpx  missing   20.0 s of 80 s: 11:05:30Z – 11:05:50Z", out)
        self.assertIn("GS010004.gpx  no GPS    50 s", out)
        self.assertIn("GS010005.gpx  missing   20.0 s of 60 s: 11:09:00Z – 11:09:20Z", out)
        self.assertIn("4 of 5 clip(s) still have missing data", out)
        self.assertEqual({n: (d / n).read_bytes() for n in names}, before)

    # -- filling -----------------------------------------------------------------
    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_head_gap_is_filled_from_skydemon_before_flightradar24(self):
        d = self.folder("GS010002.gpx", "fl01_aaaa0001.kml", "aaaa0001.csv", "SD_TEST.gpx")
        r = self.run_check(d, "GS010002.gpx", answers="\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        offers = [line for line in r.stdout.splitlines() if "covers" in line]
        self.assertEqual(len(offers), 2, r.stdout)                 # Flightradar24 offered once
        self.assertIn("SD_TEST.gpx", offers[0])
        self.assertIn("SkyDemon", offers[0])
        self.assertIn("Flightradar24", offers[1])
        self.assertIn("matched to the camera: altitude +5 ft", r.stdout)
        self.assertTrue((d / "GS010002.gpx.orig").exists())
        pts = self.pts(d / "GS010002.gpx")
        self.assertEqual(T.fmt_time(pts[0].t), "2026-10-17T11:03:20Z")
        self.assertEqual(T.fmt_time(pts[-1].t), "2026-10-17T11:04:20Z")
        self.assertEqual({p.src for p in pts if p.src}, {"SD_TEST.gpx"})
        self.assertTrue(all(p.t < at(230.05) for p in pts if p.src))
        self.assertTrue(all(p.spd is not None for p in pts if p.src))
        self.assertSmoothSeam(pts)

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_middle_gap_meets_the_camera_on_both_sides(self):
        d = self.folder("GS010003.gpx", "fl01_aaaa0001.kml")
        r = self.run_check(d, "GS010003.gpx", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("matched to the camera: altitude +190 ft", r.stdout)
        pts = self.pts(d / "GS010003.gpx")
        filled = [p for p in pts if p.src]
        self.assertTrue(filled)
        self.assertTrue(all(at(330) < p.t < at(350) for p in filled))
        for p in filled:                                        # at the camera's GPS altitude
            fr = T.interp(self.fr.pts, self.fr.times, p.t)
            self.assertAlmostEqual((p.ele - fr.ele) / T.FT, CAM_FT, delta=6)
        self.assertSmoothSeam(pts)

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_empty_clip_takes_its_altitude_from_the_neighbouring_clips(self):
        d = self.folder("GS010003.gpx", "GS010004.gpx", "GS010005.gpx", "fl01_aaaa0001.kml")
        r = self.run_check(d, "GS010004.gpx", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("altitude matched to the camera's GPS (+190 ft, from GS010003.gpx, GS010005.gpx)",
                      r.stdout)
        pts = self.pts(d / "GS010004.gpx")
        self.assertTrue(all(p.src == "fl01_aaaa0001.kml" for p in pts))
        for p in pts:
            fr = T.interp(self.fr.pts, self.fr.times, p.t)
            self.assertAlmostEqual((p.ele - fr.ele) / T.FT, CAM_FT, delta=3)

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_empty_clip_alone_keeps_the_sources_altitude(self):
        d = self.folder("GS010004.gpx", "fl01_aaaa0001.kml")
        r = self.run_check(d, "GS010004.gpx", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("altitude not matched", r.stdout)
        for p in self.pts(d / "GS010004.gpx"):
            fr = T.interp(self.fr.pts, self.fr.times, p.t)
            self.assertAlmostEqual(p.ele, fr.ele, delta=0.06)

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_tail_gap_partly_covered_stays_missing(self):
        d = self.folder("GS010005.gpx", "SD_TEST.gpx")              # SkyDemon ends at 300 s
        r = self.run_check(d, "GS010005.gpx", "--yes")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("The gap is left as it is", r.stdout)
        d = self.folder("GS010005.gpx", "fl01_aaaa0001.kml")
        r = self.run_check(d, "GS010005.gpx", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pts = self.pts(d / "GS010005.gpx")
        self.assertEqual(T.fmt_time(pts[-1].t), "2026-10-17T11:09:20Z")
        self.assertSmoothSeam(pts)

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_whole_folder_at_once_and_a_rerun_finds_it_complete(self):
        names = [f"{n}.gpx" for n in CLIPS]
        d = self.folder(*names, "fl01_aaaa0001.kml")
        r = self.run_check(d, ".", "--yes", lang="sv")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Kontrollerar 5 klipp", r.stdout)
        self.assertIn("Alla klipp har data för hela sin längd (kontrollerade: 5)", r.stdout)
        again = self.run_check(d, ".", answers="")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(again.stdout.count("  complete"), 5, again.stdout)
        self.assertIn("30.0 s filled earlier from fl01_aaaa0001.kml", again.stdout)

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_refill_redoes_a_fill_and_keeps_the_camera_points(self):
        d = self.folder("GS010002.gpx", "fl01_aaaa0001.kml", "SD_TEST.gpx")
        self.run_check(d, "GS010002.gpx", "--fill", "fl01_aaaa0001.kml", "--no-ask")
        self.assertEqual({p.src for p in self.pts(d / "GS010002.gpx") if p.src}, {"fl01_aaaa0001.kml"})
        orig = (d / "GS010002.gpx.orig").read_bytes()
        r = self.run_check(d, "GS010002.gpx", "--refill", answers="1\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pts = self.pts(d / "GS010002.gpx")
        self.assertEqual({p.src for p in pts if p.src}, {"SD_TEST.gpx"})
        self.assertEqual(sum(1 for p in pts if p.src is None), 301)    # 230.0–260.0 s at 10 Hz
        self.assertEqual((d / "GS010002.gpx.orig").read_bytes(), orig)  # the original is kept

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_answers_another_file_a_bad_file_and_no(self):
        d = self.folder("GS010003.gpx")                               # nothing to offer
        (d / "elsewhere").mkdir()
        shutil.copy(self.lib / "aaaa0001.csv", d / "elsewhere" / "track.csv")
        r = self.run_check(d, "GS010003.gpx", answers="nonexistent.kml\nelsewhere/track.csv\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("File to fill from", r.stdout)
        self.assertIn("Could not use nonexistent.kml", r.stdout)
        self.assertIn("from track.csv", r.stdout)
        d = self.folder("GS010003.gpx", "fl01_aaaa0001.kml")
        before = (d / "GS010003.gpx").read_bytes()
        r = self.run_check(d, "GS010003.gpx", answers="n\n")
        self.assertEqual(r.returncode, 3)
        self.assertEqual((d / "GS010003.gpx").read_bytes(), before)

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_output_elsewhere_leaves_the_camera_file(self):
        d = self.folder("GS010003.gpx", "fl01_aaaa0001.kml")
        before = (d / "GS010003.gpx").read_bytes()
        r = self.run_check(d, "GS010003.gpx", "--yes", "-o", "full.gpx")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((d / "GS010003.gpx").read_bytes(), before)
        self.assertTrue(any(p.src for p in self.pts(d / "full.gpx")))

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_camera_clock_on_local_time_is_followed(self):
        d = self.folder("GS010003.gpx", "fl01_aaaa0001.kml")
        db = json.loads((self.lib / "db.json").read_text())
        db["GS010003.360"][0] = T.fmt_time(at(300 + 7200)).replace("Z", ".000000Z")   # UTC+2 clock
        (d / "db.json").write_text(json.dumps(db))
        env = dict(os.environ, GOPRO_LANG="en", STUB_FFPROBE_DB=str(d / "db.json"))
        r = subprocess.run([sys.executable, str(SCRIPT), "--check", "GS010003.gpx", "--yes",
                            "--video-dir", str(d / "card"), "--ffprobe", str(self.lib / "ffprobe_stub")],
                           capture_output=True, text=True, cwd=d, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("the camera clock is -7200.0 s off GPS time", r.stdout)
        self.assertIn("missing   20.0 s of 80 s: 11:05:30Z – 11:05:50Z", r.stdout)

    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_a_clip_without_video_is_an_error_but_the_rest_runs(self):
        d = self.folder("GS010001.gpx", "fl01_aaaa0001.kml")
        shutil.copy(self.lib / "GS010001.gpx", d / "GS019999.gpx")
        r = self.run_check(d, ".", "--no-ask")
        self.assertEqual(r.returncode, 1)
        self.assertIn("GS010001.gpx  complete", r.stdout)
        self.assertIn("GS019999.gpx  error     no video GS019999.360 or .mp4", r.stdout)

    def test_check_options_need_check(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "a.kml", "b.gpx", "--start", "11:00:00",
                            "--duration", "5", "--fill", "x.kml"], capture_output=True, text=True,
                           env=dict(os.environ, GOPRO_LANG="en"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("--fill works with --check", r.stderr)

    def test_placeholder_is_recognised(self):
        track = T.load_track(self.lib / "GS010002.gpx")
        pts, ph = T.drop_placeholder(track.pts, 2.0)
        self.assertIsNotNone(ph)
        self.assertEqual(T.fmt_time(ph.t), "2026-10-17T11:03:20.030Z")
        self.assertEqual(T.fmt_time(pts[0].t), "2026-10-17T11:03:50Z")
        complete = T.load_track(self.lib / "GS010001.gpx").pts
        self.assertIsNone(T.drop_placeholder(complete, 2.0)[1])

    # -- Flightradar24's KML/CSV also saved as GPX (gpsbabel) ---------------------
    @unittest.skipIf(os.name == "nt", "the stubs need a POSIX shebang")
    def test_flightradar24_files_are_saved_as_gpx_once_and_from_the_csv(self):
        d = self.folder("GS010002.gpx", "aaaa0001.csv")
        shutil.copy(self.lib / "fl01_aaaa0001.kml", d / "aaaa0001.kml")   # same flight, both files
        r = self.run_check(d, ".", "--yes", "--fill", "aaaa0001.kml")     # the KML is read first
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("from aaaa0001.kml", r.stdout)
        self.assertIn("Saved as GPX: aaaa0001.csv → aaaa0001.gpx (2 points, gpsbabel)", r.stdout)
        calls = self.babel_calls(d)
        self.assertEqual(len(calls), 1, calls)
        self.assertIn("-i xcsv,style=", calls[0])
        self.assertIn(f"-f {d.resolve() / 'aaaa0001.csv'} ", calls[0])

        r = self.run_check(d, ".", "--yes")       # nothing left to fill, and up to date
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Saved as GPX", r.stdout)
        later = (d / "aaaa0001.gpx").stat().st_mtime + 60
        os.utime(d / "aaaa0001.csv", (later, later))
        r = self.run_check(d, ".", "--yes")       # a newer export is saved again
        self.assertIn("Saved as GPX: aaaa0001.csv → aaaa0001.gpx", r.stdout)
        self.assertEqual(len(self.babel_calls(d)), 2)

    @unittest.skipIf(os.name == "nt", "the stubs need a POSIX shebang")
    def test_a_gpx_gpsbabel_did_not_make_is_never_written_over(self):
        d = self.folder("GS010001.gpx", "aaaa0001.csv")
        mine = d / "aaaa0001.gpx"
        T.write_gpx(mine, self.fr.pts[:5], "mine")
        old = (d / "aaaa0001.csv").stat().st_mtime - 600
        os.utime(mine, (old, old))
        before = mine.read_bytes()
        r = self.run_check(d, ".", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[WARNING] aaaa0001.gpx was not made by gpsbabel, so aaaa0001.csv "
                      "is not saved as GPX over it.", r.stdout)
        self.assertEqual(mine.read_bytes(), before)
        self.assertEqual(self.babel_calls(d), [])

    @unittest.skipIf(os.name == "nt", "the stubs need a POSIX shebang")
    def test_dry_run_saves_no_gpx_and_gpsbabel_trouble_is_only_a_warning(self):
        d = self.folder("GS010001.gpx", "fl01_aaaa0001.kml")
        r = self.run_check(d, ".", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.babel_calls(d), [])
        self.assertFalse((d / "fl01_aaaa0001.gpx").exists())

        r = self.run_check(d, ".", "--yes", "--gpsbabel", d / "no-such-gpsbabel")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("gpsbabel not found", r.stdout)
        self.assertIn("so fl01_aaaa0001.kml is not saved as GPX", r.stdout)

        r = self.run_check(d, ".", "--yes", env={"STUB_GPSBABEL_FAIL": "kml: no such file"},
                           lang="sv")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[VARNING] gpsbabel kunde inte spara fl01_aaaa0001.kml som GPX: "
                      "kml: no such file", r.stdout)
        self.assertEqual(sorted(f.name for f in d.iterdir() if "fl01" in f.name),
                         ["fl01_aaaa0001.kml"])      # no GPX, no half-written .part

    def test_the_folder_offers_the_original_rather_than_gpsbabels_copy(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp.name))
        shutil.copy(self.lib / "aaaa0001.csv", d / "aaaa0001.csv")
        # what gpsbabel makes of the CSV: GPX 1.0 with <speed>/<course>, no Flightradar24 text
        body = "".join(f'<trkpt lat="{p.lat:.9f}" lon="{p.lon:.9f}"><ele>{p.ele:.3f}</ele>'
                       f'<time>{T.fmt_time(p.t)}</time><course>{p.crs:.6f}</course>'
                       f'<speed>{p.spd:.6f}</speed><name>SETST</name></trkpt>'
                       for p in T.load_track(d / "aaaa0001.csv").pts)
        (d / "aaaa0001.gpx").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.0" creator="GPSBabel - '
            'https://www.gpsbabel.org" xmlns="http://www.topografix.com/GPX/1/0">'
            f'<trk><trkseg>{body}</trkseg></trk></gpx>\n')
        args = argparse.Namespace(search=[], fill=[])
        self.assertEqual([s.name for s in T.Sources(args, [d]).discovered()], ["aaaa0001.csv"])

    @unittest.skipUnless(shutil.which("gpsbabel"), "gpsbabel is not installed")
    def test_real_gpsbabel_keeps_every_point_of_the_kml_and_of_the_csv(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp.name))
        rows = synthetic_flight()
        write_fr24_kml(d / "fr.kml", rows)
        write_fr24_csv(d / "fr2.csv", rows)
        lines = T.save_fr24_gpx([T.load_track(d / "fr.kml"), T.load_track(d / "fr2.csv")],
                                "gpsbabel")
        self.assertEqual(lines, ["Saved as GPX: fr.kml → fr.gpx (400 points, gpsbabel)",
                                 "Saved as GPX: fr2.csv → fr2.gpx (400 points, gpsbabel)"])
        for name in ("fr.gpx", "fr2.gpx"):
            text = (d / name).read_text()
            self.assertNotIn("<wpt", text)                  # one timed track, nothing else
            self.assertEqual(text.count("<trk>"), 1)
            got = T.load_track(d / name).pts
            self.assertEqual(len(got), len(rows))
            for p, (tm, lat, lon, alt, kt, hdg) in zip(got, rows):
                self.assertEqual((p.t, round(p.lat, 6), round(p.lon, 6)), (tm, lat, lon))
                self.assertAlmostEqual(p.ele / T.FT, alt, delta=0.1)
                self.assertAlmostEqual(p.spd / T.KT, kt, delta=0.01)
                self.assertAlmostEqual(p.crs, hdg, delta=0.01)
        self.assertIn("<speed>", (d / "fr2.gpx").read_text())   # the CSV's speed as GPX 1.0


if __name__ == "__main__":
    unittest.main()
