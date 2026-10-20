#!/usr/bin/env python3
"""Tests for trim_gpx.py - standard library only: no network, no ffmpeg.

Run from the repository root:

    python3 -m unittest discover -s tests -v

The flight is synthetic but shaped like a Flightradar24 export: whole-second
timestamps every 2-3 s, integer knots and degrees, altitude in 100 ft steps,
and a right turn through north. ffprobe and gpsbabel are replaced by stubs, so
the --video tests need no video files (they are skipped on Windows, where the
stubs cannot be run directly).
"""
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "trim_gpx.py"
GPX = "{http://www.topografix.com/GPX/1/1}"
TPX = "{http://www.garmin.com/xmlschemas/TrackPointExtension/v2}"
KT = 0.514444
T0 = datetime(2026, 10, 17, 11, 0, 0, tzinfo=timezone.utc)


def synthetic_flight(n=400):
    """(time, lat, lon, alt_ft, speed_kt, heading) rows, Flightradar24 style."""
    rows, sec, lat, lon = [], 0, 56.0, 13.0
    for i in range(n):
        kt = round(90 + 30 * i / n)
        hdg = round(330 + i * 0.5) % 360            # passes north around i = 60
        alt = 700 + 100 * (i // 150)
        rows.append((T0 + timedelta(seconds=sec), round(lat, 6), round(lon, 6), alt, kt, hdg))
        dt = (2, 2, 3)[i % 3]
        d = kt * KT * dt
        lat += d * math.cos(math.radians(hdg)) / 111320
        lon += d * math.sin(math.radians(hdg)) / (111320 * math.cos(math.radians(lat)))
        sec += dt
    return rows


def write_fr24_kml(path, rows):
    trail = []
    for tm, lat, lon, alt, kt, hdg in rows:
        trail.append(f"""      <Placemark>
        <name>{tm:%Y-%m-%d %H:%M:%S} UTC</name>
        <description><![CDATA[<div><div><span><b>Altitude:</b></span> <span>{alt:,} ft</span></div>
<div><span><b>Speed:</b></span> <span>{kt} kt</span></div>
<div><span><b>Heading:</b></span> <span>{hdg}&deg;</span></div>
</div>]]></description>
        <TimeStamp>
          <when>{tm:%Y-%m-%dT%H:%M:%S}+00:00</when>
        </TimeStamp>
        <Style>
          <IconStyle>
            <heading>{hdg}</heading>
          </IconStyle>
        </Style>
        <Point>
          <altitudeMode>absolute</altitudeMode>
          <coordinates>{lon},{lat},{alt * 0.3048:.2f}</coordinates>
        </Point>
      </Placemark>""")
    route = " ".join(f"{lon},{lat},{alt * 0.3048:.2f}" for _, lat, lon, alt, _, _ in rows)
    path.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>-/SETST</name>
    <Folder>
      <name>Route</name>
      <Placemark>
        <LineString>
          <altitudeMode>absolute</altitudeMode>
          <coordinates>{route}</coordinates>
        </LineString>
      </Placemark>
    </Folder>
    <Folder>
      <name>Trail</name>
{chr(10).join(trail)}
    </Folder>
  </Document>
</kml>
""", encoding="utf-8")


def write_fr24_csv(path, rows):
    lines = ["Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction"]
    for tm, lat, lon, alt, kt, hdg in rows:
        lines.append(f'{int(tm.timestamp())},{tm:%Y-%m-%dT%H:%M:%SZ},SETST,"{lat},{lon}",{alt},{kt},{hdg}')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_babel_gpx(path, rows, with_desc=True):
    """What gpsbabel 1.9 makes of a Flightradar24 KML: timed <wpt> carrying the
    point description as escaped HTML in <cmt>/<desc>, plus an untimed <trk>.
    with_desc=False gives a plain GPX with positions and times only."""
    def desc(alt, kt, hdg):
        html = (f"<div><div><span><b>Altitude:</b></span> <span>{alt:,} ft</span></div>\n"
                f"<div><span><b>Speed:</b></span> <span>{kt} kt</span></div>\n"
                f"<div><span><b>Heading:</b></span> <span>{hdg}&deg;</span></div>\n</div>")
        html = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"<cmt>{html}</cmt><desc>{html}</desc>" if with_desc else ""
    wpts = "\n".join(f'<wpt lat="{lat:.9f}" lon="{lon:.9f}"><ele>{alt * 0.3048:.3f}</ele>'
                     f'<time>{tm:%Y-%m-%dT%H:%M:%SZ}</time><name>{tm:%Y-%m-%d %H:%M:%S} UTC</name>'
                     f'{desc(alt, kt, hdg)}</wpt>'
                     for tm, lat, lon, alt, kt, hdg in rows)
    path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<gpx version="1.0" creator="GPSBabel" xmlns="http://www.topografix.com/GPX/1/0">\n'
                    f'{wpts}\n<trk><name>SETST</name><trkseg><trkpt lat="56" lon="13"/></trkseg></trk>\n'
                    '</gpx>\n', encoding="utf-8")


STUB_FFPROBE = """#!/usr/bin/env python3
import json, os, sys
db = json.load(open(os.environ["STUB_FFPROBE_DB"]))
name = os.path.basename(sys.argv[-1])
if name not in db:
    print(sys.argv[-1] + ": Invalid data found when processing input", file=sys.stderr)
    sys.exit(1)
ct, dur = db[name]
fmt = {"duration": "%.6f" % dur}
if ct:
    fmt["tags"] = {"creation_time": ct}
print(json.dumps({"format": fmt}))
"""

STUB_GPSBABEL = """#!/usr/bin/env python3
# Stands in for gpsbabel: notes its arguments, then writes a small GPX where -F
# says (or half of one and fails, when STUB_GPSBABEL_FAIL is set).
import os, sys
log = os.environ.get("STUB_GPSBABEL_LOG")
if log:
    with open(log, "a") as f:
        f.write(" ".join(sys.argv[1:]) + "\\n")
out = sys.argv[sys.argv.index("-F") + 1]
if os.environ.get("STUB_GPSBABEL_FAIL"):
    with open(out, "w") as f:
        f.write('<?xml version="1.0"?><gpx creator="GPSBabel')
    print(os.environ["STUB_GPSBABEL_FAIL"], file=sys.stderr)
    sys.exit(1)
with open(out, "w") as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\\n<gpx version="1.0" '
            'creator="GPSBabel - https://www.gpsbabel.org" xmlns="http://www.topografix.com/GPX/1/0">'
            '<trk><trkseg><trkpt lat="1" lon="1"><time>2000-01-01T00:00:00Z</time></trkpt>'
            '<trkpt lat="1" lon="1.001"><time>2000-01-01T00:00:02Z</time></trkpt>'
            '</trkseg></trk></gpx>\\n')
"""


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class TrimGpxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.rows = synthetic_flight()
        write_fr24_kml(cls.dir / "flight.kml", cls.rows)
        write_fr24_csv(cls.dir / "flight.csv", cls.rows)
        write_babel_gpx(cls.dir / "babel.gpx", cls.rows)
        write_babel_gpx(cls.dir / "plain.gpx", cls.rows, with_desc=False)
        cls.last = cls.rows[-1][0]
        stub = cls.dir / "gpsbabel_stub"
        stub.write_text(STUB_GPSBABEL)
        stub.chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_tool(self, *args, lang="en", env=None):
        """The script, with the stub gpsbabel unless the test gives --gpsbabel."""
        e = dict(os.environ, GOPRO_LANG=lang, STUB_GPSBABEL_LOG=str(self.dir / "gpsbabel.log"))
        e.update(env or {})
        cmd = [sys.executable, str(SCRIPT), "--gpsbabel", str(self.dir / "gpsbabel_stub")]
        return subprocess.run(cmd + list(map(str, args)),
                              capture_output=True, text=True, cwd=self.dir, env=e)

    def points(self, name):
        root = ET.parse(self.dir / name).getroot()
        out = []
        for p in root.iter(GPX + "trkpt"):
            spd, crs = p.find(f".//{TPX}speed"), p.find(f".//{TPX}course")
            out.append((p.find(GPX + "time").text, float(p.get("lat")), float(p.get("lon")),
                        float(spd.text) if spd is not None else None,
                        float(crs.text) if crs is not None else None))
        return out

    # -- the window -------------------------------------------------------------
    def test_kml_window_is_exact(self):
        start = T0 + timedelta(seconds=100.5)
        r = self.run_tool("flight.kml", "a.gpx", "--start", start.isoformat(), "--duration", "62.208")
        self.assertEqual(r.returncode, 0, r.stderr)
        pts = self.points("a.gpx")
        self.assertEqual(pts[0][0], "2026-10-17T11:01:40.500Z")
        self.assertEqual(pts[-1][0], "2026-10-17T11:02:42.708Z")
        inside = [row for row in self.rows if start < row[0] < start + timedelta(seconds=62.208)]
        self.assertEqual(len(pts), len(inside) + 2)
        self.assertIn("measured in the source", r.stdout)

    def test_speed_and_course_written_as_measured(self):
        r = self.run_tool("flight.kml", "b.gpx", "--start", iso(T0 + timedelta(seconds=300)),
                          "--duration", "30")
        self.assertEqual(r.returncode, 0, r.stderr)
        by_time = {iso(row[0]): row for row in self.rows}
        checked = 0
        for tm, _, _, spd, crs in self.points("b.gpx"):
            self.assertIsNotNone(spd)
            self.assertIsNotNone(crs)
            if tm in by_time:
                self.assertAlmostEqual(spd, by_time[tm][4] * KT, delta=0.006)
                self.assertAlmostEqual(crs, by_time[tm][5] % 360, delta=0.06)
                checked += 1
        self.assertGreater(checked, 5)

    def test_csv_and_gpsbabel_output_give_the_same_gpx_as_kml(self):
        args = ["--start", iso(T0 + timedelta(seconds=200)), "--duration", "45.5"]
        for d, src in (("k", "flight.kml"), ("c", "flight.csv"), ("b", "babel.gpx")):
            (self.dir / d).mkdir(exist_ok=True)
            r = self.run_tool(src, f"{d}/x.gpx", *args)
            self.assertEqual(r.returncode, 0, r.stderr)
        kml = (self.dir / "k/x.gpx").read_bytes()
        self.assertIn(b"gpxtpx:speed", kml)
        self.assertEqual(kml, (self.dir / "c/x.gpx").read_bytes())
        self.assertEqual(kml, (self.dir / "b/x.gpx").read_bytes())

    def test_gpx_without_speed_gets_no_extensions(self):
        r = self.run_tool("plain.gpx", "c.gpx", "--start", iso(T0 + timedelta(seconds=60)),
                          "--duration", "20")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.dir / "c.gpx").read_text()
        self.assertNotIn("extensions", text)
        self.assertNotIn("gpxtpx", text)
        self.assertIn("derived from the positions", r.stdout)

    def test_course_turns_through_north_the_short_way(self):
        r = self.run_tool("flight.kml", "d.gpx", "--start", iso(T0 + timedelta(seconds=120)),
                          "--duration", "40", "--hz", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        courses = [p[4] for p in self.points("d.gpx")]
        self.assertTrue(any(c > 350 for c in courses) and any(c < 10 for c in courses), courses)
        self.assertFalse(any(30 < c < 330 for c in courses), courses)

    def test_resampling_is_regular_and_ends_exactly(self):
        r = self.run_tool("flight.kml", "e.gpx", "--start", iso(T0 + timedelta(seconds=50)),
                          "--duration", "10.25", "--hz", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        times = [p[0] for p in self.points("e.gpx")]
        self.assertEqual(times[0], "2026-10-17T11:00:50Z")
        self.assertEqual(times[1], "2026-10-17T11:00:50.500Z")
        self.assertEqual(times[-2], "2026-10-17T11:01:00Z")
        self.assertEqual(times[-1], "2026-10-17T11:01:00.250Z")
        self.assertEqual(len(times), 22)

    def test_time_of_day_takes_the_tracks_date(self):
        a = self.run_tool("flight.kml", "f1.gpx", "--start", "11:01:40", "--duration", "1:02")
        b = self.run_tool("flight.kml", "f1.gpx", "--start", "2026-10-17T11:01:40Z", "--duration", "62")
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertEqual(a.stdout, b.stdout)

    def test_exiftool_time_format(self):
        r = self.run_tool("flight.kml", "f2.gpx", "--start", "2026:10:17 11:01:40", "--duration", "5")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.points("f2.gpx")[0][0], "2026-10-17T11:01:40Z")

    # -- time zones -------------------------------------------------------------
    def test_wrong_tz_is_caught_and_the_right_one_suggested(self):
        r = self.run_tool("flight.kml", "g.gpx", "--start", iso(T0 + timedelta(seconds=100)),
                          "--duration", "30", "--tz", "2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("entirely outside the track", r.stderr)
        self.assertIn("Without --tz the window lands at 11:01:40Z", r.stderr)
        self.assertFalse((self.dir / "g.gpx").exists())

    def test_local_camera_clock_needs_tz(self):
        local = (T0 + timedelta(hours=2, seconds=100)).strftime("%H:%M:%S")
        r = self.run_tool("flight.kml", "h.gpx", "--start", local, "--duration", "30")
        self.assertEqual(r.returncode, 2)
        self.assertIn("With --tz 2 the window lands at 11:01:40Z", r.stderr)
        r = self.run_tool("flight.kml", "h.gpx", "--start", local, "--duration", "30", "--tz", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.points("h.gpx")[0][0], "2026-10-17T11:01:40Z")

    def test_partly_outside_warns_and_holds_the_track_end(self):
        end = self.last + timedelta(seconds=20)
        r = self.run_tool("flight.kml", "i.gpx", "--start", iso(self.last - timedelta(seconds=10)),
                          "--duration", "30")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[WARNING] The track only covers", r.stdout)
        self.assertIn("The GPX still spans the whole clip", r.stdout)
        pts = self.points("i.gpx")                    # the GPX ends with the clip, not the track
        self.assertEqual((pts[-2][0], pts[-1][0]), (iso(self.last), iso(end)))
        self.assertEqual(pts[-1][1:3], pts[-2][1:3])  # the track's last position, held
        self.assertEqual(pts[-1][3:], (None, None))   # no speed or course: nothing was measured
        self.assertEqual((self.dir / "i.gpx").read_text().count("<src>hold</src>"), 1)

    # -- --video with a stub ffprobe ----------------------------------------------
    @unittest.skipIf(os.name == "nt", "the stub ffprobe needs a POSIX shebang")
    def test_video_and_gopro_chapters(self):
        stub = self.dir / "ffprobe_stub"
        stub.write_text(STUB_FFPROBE)
        stub.chmod(0o755)
        db = {
            "GS010132.360": ["2026-10-17T11:05:07.000000Z", 62.208],
            "GS010068.360": ["2026-10-17T11:02:00.000000Z", 10.0],    # chapters carry the
            "GS020068.360": ["2026-10-17T11:02:00.000000Z", 8.0],     # recording's start
            "GS030068.360": ["2026-10-17T11:02:00.000000Z", 4.0],
            "GS010069.360": ["2026-10-17T11:06:00.000000Z", 10.0],    # chapters carry
            "GS020069.360": ["2026-10-17T11:06:10.000000Z", 8.0],     # their own start
            "GS020070.360": ["2026-10-17T11:08:00.000000Z", 8.0],     # chapter 1 missing
            "nodate.mp4": [None, 5.0],
        }
        (self.dir / "db.json").write_text(json.dumps(db))
        for name in db:
            (self.dir / name).write_bytes(b"")
        env = {"STUB_FFPROBE_DB": str(self.dir / "db.json")}

        def run(video, *extra):
            return self.run_tool("flight.kml", "v.gpx", "--video", video, "--ffprobe", stub,
                                 *extra, env=env)

        r = run("GS010132.360")
        self.assertEqual(r.returncode, 0, r.stderr)
        pts = self.points("v.gpx")
        self.assertEqual((pts[0][0], pts[-1][0]), ("2026-10-17T11:05:07Z", "2026-10-17T11:06:09.208Z"))

        r = run("GS030068.360")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("adding the 2 earlier chapter(s) (18 s)", r.stdout)
        self.assertEqual(self.points("v.gpx")[0][0], "2026-10-17T11:02:18Z")

        r = run("GS020069.360")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("chapter", r.stdout)
        self.assertEqual(self.points("v.gpx")[0][0], "2026-10-17T11:06:10Z")

        r = run("GS020070.360")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[WARNING] GS020070.360 is chapter 2", r.stdout)

        r = run("GS010132.360", "--start", "11:05:10")
        self.assertEqual(r.returncode, 0, r.stderr)
        pts = self.points("v.gpx")
        self.assertEqual((pts[0][0], pts[-1][0]), ("2026-10-17T11:05:10Z", "2026-10-17T11:06:12.208Z"))

        r = run("nodate.mp4")
        self.assertEqual(r.returncode, 1)
        self.assertIn("has no creation_time", r.stderr)

        r = run("missing.360")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ffprobe could not read missing.360", r.stderr)

        r = self.run_tool("flight.kml", "v.gpx", "--video", "GS010132.360",
                          "--ffprobe", self.dir / "no-such-ffprobe")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ffprobe not found", r.stderr)

    # -- language and errors ------------------------------------------------------
    def test_swedish_from_environment_and_lang_flag_wins(self):
        args = ["flight.kml", "j.gpx", "--start", iso(T0 + timedelta(seconds=60)), "--duration", "9"]
        sv = self.run_tool(*args, lang="sv")
        self.assertIn("Fönster:", sv.stdout)
        self.assertIn("Sparade", sv.stdout)
        en = self.run_tool(*args, "--lang", "en", lang="sv")
        self.assertIn("Window:", en.stdout)

    def test_bad_input_files(self):
        (self.dir / "bad.csv").write_text("a,b,c\n1,2,3\n")
        r = self.run_tool("bad.csv", "k.gpx", "--start", "11:00:00", "--duration", "5")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no time and position columns", r.stderr)

        (self.dir / "bad2.csv").write_text(
            "Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction\n"
            '1,2026-10-17T11:00:00Z,X,"56.1,13.2",700,90,10\n'
            '2,nonsense,X,"56.2,13.2",700,90,10\n')
        r = self.run_tool("bad2.csv", "k.gpx", "--start", "11:00:00", "--duration", "5")
        self.assertEqual(r.returncode, 1)
        self.assertIn("line 3: unknown time format", r.stderr)

        r = self.run_tool("no-such-file.kml", "k.gpx", "--start", "11:00:00", "--duration", "5")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Could not read no-such-file.kml", r.stderr)

        r = self.run_tool("flight.kml", "k.gpx", "--duration", "5")
        self.assertEqual(r.returncode, 2)
        self.assertIn("give --video, or both --start and --duration", r.stderr)

    # -- a Flightradar24 file is also saved as GPX (gpsbabel) ----------------------
    @unittest.skipIf(os.name == "nt", "the stub gpsbabel needs a POSIX shebang")
    def test_cutting_saves_the_track_as_gpx_but_never_over_its_output(self):
        d = Path(tempfile.mkdtemp(dir=self.dir))
        write_fr24_csv(d / "fr.csv", self.rows)
        log = {"STUB_GPSBABEL_LOG": str(d / "log")}
        when = ["--start", iso(T0 + timedelta(seconds=60)), "--duration", "9"]

        r = self.run_tool(d / "fr.csv", d / "fr.gpx", *when, env=log)    # OUTPUT is that GPX
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((d / "log").exists())
        self.assertIn('creator="trim_gpx.py"', (d / "fr.gpx").read_text())

        (d / "fr.gpx").unlink()
        r = self.run_tool(d / "fr.csv", d / "cut.gpx", *when, env=log)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Saved as GPX: fr.csv → fr.gpx (2 points, gpsbabel)", r.stdout)
        call = (d / "log").read_text()
        self.assertIn("-i xcsv,style=", call)
        self.assertIn("-x transform,trk=wpt,del -o gpx -F", call)

        r = self.run_tool(d / "fr.csv", d / "cut.gpx", *when, env=log)     # up to date
        self.assertNotIn("Saved as GPX", r.stdout)
        self.assertEqual(len((d / "log").read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
