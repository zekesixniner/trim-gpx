# trim-gpx

Makes sure every GoPro clip has GPS telemetry for its whole length. It checks
the GPX extracted from each clip against the clip itself, and fills what is
missing from another track — a [SkyDemon](https://www.skydemon.aero) log
first, a [Flightradar24](https://www.flightradar24.com) track second — while
the camera's own points stay wherever it has them. The result goes into
[OVRLEY](https://www.ovrley.cc) like any other clip's telemetry.

It can also cut any track down to exactly one clip.

🇸🇪 [Svensk version av denna README](README.sv.md) ·
📖 [Manual: complete a clip's GPS](MANUAL.md) / [Manual på svenska](MANUAL.sv.md)

```bash
cd /path/to/the/flight          # the clips' GPX files, plus SkyDemon/Flightradar24 tracks
trim_gpx.py --check . --video-dir /mnt/e/DCIM/100GOPRO
```

```
Checking 1 clip(s), videos in /mnt/e/DCIM/100GOPRO:
  GS010130.gpx  missing   63.1 s of 203.093 s: 10:00:27Z – 10:01:30Z · camera clock +0.03 s

GS010130.gpx: missing 10:00:27Z – 10:01:30Z (63.1 s of 203.093 s)
  Fill from:
    1  fl02_42294bf5.gpx  Flightradar24  covers 63.1 s of 63.1 s
  Choose 1–1 (Enter = 1), another file, or n to leave the gap:
  ✓ 63.1 s from fl02_42294bf5.gpx (30 points); matched to the camera: altitude +182 ft, position 3 m
  ✅ GS010130.gpx updated: 1401 camera points + 30 filled (original: GS010130.gpx.orig)

Every clip has data for its whole length (1 checked).
```

## What it does

**Checking a clip's own GPX** (`--check`)

- **Finds what is missing.** Each GPX is compared with its clip's
  `creation_time` and length (from the `.360`, read with ffprobe): a clip with
  no fix at all, one that waited for a fix, or one with a dropout of more than
  2 seconds.
- **Sees through gopro-telemetry's placeholder.** gopro-telemetry starts its GPX
  with a copy of the first fix, dated to the first frame. After a long wait for
  a fix that point sits far from where the camera was, and OVRLEY stands still
  on it until the real data starts. It is removed.
- **Checks the camera's clock.** That placeholder carries the GPS time of the
  first frame, so the camera clock can be compared with GPS time for every clip
  that has a fix.
- **Offers what can fill the gap.** It looks next to the clips for tracks that
  cover the missing time, offers a SkyDemon log before a Flightradar24 track,
  and asks before using one. `--fill` names a track yourself, and `--yes` takes
  the best one without asking.
- **Lines the fill up with the camera.** At each seam, the filled stretch is
  moved to meet the camera's position and GPS altitude: Flightradar24's
  barometric altitude was 182 ft below the camera's GPS altitude in the example
  above. A clip with no fix of its own gets the altitude difference from the
  neighbouring clips.
- **Updates the clip's GPX in place**, keeping the original as `.gpx.orig`, so
  OVRLEY and gopro-max-gpx-pipeline find it under the usual name. Filled points
  carry their source in `<src>`.
- **Takes a whole folder at once**: one line per clip, questions only for the
  clips with gaps. Clips filled earlier count as complete.

**Cutting a track to a clip**

- **Reads Flightradar24's exports as they are**, KML or CSV, as well as any
  GPX 1.0/1.1 or KML with timestamps, and gpsbabel's conversion of a
  Flightradar24 KML.
- **Cuts exactly**: the first and last point are interpolated onto the clip's
  first and last moment, to the millisecond. `--video` takes the window from
  the clip, including chapter 2, 3 … of a long recording.
- **Catches a wrong time zone**: if the window misses the track, it says which
  `--tz` would put it inside.

**Both** keep the measured speed and course of Flightradar24 and SkyDemon.
Flightradar24's timestamps are whole seconds while its points come every two
to three seconds, so a speed computed from the positions jumps about (62–166 kt
where the aircraft flew 91–125 kt). The measured values are written into every
point as a Garmin TrackPointExtension, and OVRLEY uses that speed instead of
computing its own. Python standard library only.

**Both** also save every Flightradar24 KML or CSV they read as GPX beside it,
under the same name (`4229ad6f.csv` → `4229ad6f.gpx`), for programs that want
GPX. gpsbabel does it, from the CSV when both are there, because then the speed
and course come along as GPX 1.0 `<speed>` and `<course>`. A GPX already there
is replaced only if gpsbabel made it and the export is newer, and `--dry-run`
writes none. That GPX is not for OVRLEY, which takes speed only from
extensions: give OVRLEY the filled camera GPX or a cut track.

## Requirements

- Python 3.9 or newer
- ffprobe, part of ffmpeg (`sudo apt install ffmpeg` in WSL/Ubuntu)
- gpsbabel, for saving Flightradar24's exports as GPX (`sudo apt install
  gpsbabel`); without it you get a warning and everything else works
- For filling: a SkyDemon log of the flight, or a Flightradar24 export, which
  takes an account that can export KML/CSV and an aircraft that sends ADS-B —
  see [what you need](MANUAL.md#what-you-need) in the manual

## Installation

Developed and run in WSL. No virtual environment is needed.

```bash
git clone https://github.com/zekesixniner/trim-gpx.git ~/dev/trim-gpx
ln -s ~/dev/trim-gpx/trim_gpx.py ~/bin/trim_gpx.py      # ~/bin is on PATH
trim_gpx.py --help
```

It is plain Python, so it should run on Windows too, with Python and ffprobe
installed (ffprobe comes with the gyan.dev ffmpeg build); it has not been
tested there yet. Copy the script over from WSL, again after every update:

```bash
cp ~/dev/trim-gpx/trim_gpx.py /mnt/c/Users/<you>/bin/
```

```powershell
python $HOME\bin\trim_gpx.py --help
```

## Usage

```
trim_gpx.py --check [CAMERA.gpx | FOLDER ...]  [--video-dir DIR] [--fill TRACK] [--yes] [--dry-run]
trim_gpx.py TRACK OUTPUT --video CLIP                [--tz H] [--hz N]
trim_gpx.py TRACK OUTPUT --start TIME --duration LEN [--tz H] [--hz N]
```

### Checking camera GPX

| option | |
|---|---|
| `--check` | check each camera GPX (`GS010130.gpx` …) against its clip and fill what is missing |
| `CAMERA.gpx`, `FOLDER` | the GPX files to check, or folders holding them (default: this folder) |
| `--video-dir DIR` | where the clips' `.360` files are (default: next to the GPX). An `.mp4` is used if there is no `.360`, with a warning |
| `--video CLIP` | the clip's file, for a single GPX |
| `--fill TRACK` | fill from this track first, without asking (repeatable, in order of preference) |
| `--search DIR` | also look for tracks in this folder (repeatable) |
| `-y`, `--yes` | fill from the best track found without asking |
| `--ask`, `--no-ask` | ask before filling, or never (default: ask when run in a terminal) |
| `--dry-run` | only report, change nothing |
| `--refill` | redo stretches filled by an earlier run; the camera's points are kept |
| `-o GPX`, `--output GPX` | write here instead of updating the camera GPX (a single clip) |
| `--max-gap S` | a hole in the camera's GPS longer than this counts as missing (default `2` s) |
| `--tz H` | the clips' `creation_time` is local time, UTC+H. A clip whose gopro-telemetry GPX has a fix is timed by GPS and needs no `--tz` |

Tracks offered for filling, in this order: SkyDemon logs, other GPS tracks,
Flightradar24 exports. Files from the camera (`GS…`), files written by this
script, gpsbabel's GPX of a Flightradar24 export lying beside it, and the same
flight exported several times over are left out.

Exit status: `0` every clip complete, `1` a clip could not be checked (e.g. no
video), `3` a clip still has missing data.

### Cutting a track

| option | |
|---|---|
| `TRACK` | the track: Flightradar24 KML or CSV, or any GPX/KML with times |
| `OUTPUT` | the GPX 1.1 file to write |
| `--video CLIP` | take start and length from the clip: its `creation_time` and duration, read with ffprobe. Use the camera's original file, e.g. `GS010132.360` |
| `--start TIME` | clip start: `12:05:07` (the date is taken from the track), `2026-10-17T12:05:07Z`, ffprobe's `2026-10-17T12:05:07.000000Z` or exiftool's `2026:10:17 12:05:07`. A time without a zone is UTC. Overrides `--video` |
| `--duration LEN` | clip length: `62.208` (seconds) or `1:02`. Overrides `--video` |
| `--tz H` | the start time is the camera's local clock, UTC+H: `2` for Swedish summer time, `1` for winter time. Default `0`, the camera runs on UTC |
| `--hz N` | resample to N points per second. OVRLEY does not need it |

Exit status: `0` done (also when the track covers only part of the clip, with
a warning; the GPX then holds the track's first or last position out to the
clip's ends), `1` error, `2` the window lies entirely outside the track.

### Common options

| option | |
|---|---|
| `--ffprobe PATH` | the ffprobe to use (default: `ffprobe` on PATH) |
| `--gpsbabel PATH` | the gpsbabel that saves Flightradar24's KML/CSV as GPX (default: `gpsbabel` on PATH) |
| `--lang en\|sv` | message language (default: `$GOPRO_LANG`, else English) |
| `--version` | print the version |

### Input formats

| source | what is read |
|---|---|
| camera GPX (gopro-telemetry, gpmf2gpx.py) | timed `<trkpt>`; points with `<fix>none</fix>` or fix 0 are skipped |
| SkyDemon GPX | `<trkpt>` with `<ele>`, `<speed>` (m/s) and `<time>` |
| Flightradar24 KML | the Trail placemarks: time, position and altitude; speed and heading from each point's description |
| Flightradar24 CSV | `Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction`, altitude in feet and speed in knots |
| gpsbabel's GPX of a Flightradar24 KML | the timed `<wpt>`; speed and heading from the description gpsbabel keeps in `<desc>` |
| any GPX 1.0/1.1 | timed `<trkpt>`, `<wpt>` and `<rtept>`; `<speed>` and `<course>` when present |
| other KML | `Placemark` with `TimeStamp`, and `gx:Track` |

Points without a time are skipped; Flightradar24's Route line has none.

### Output

A GPX 1.1 track with one segment, from the clip's first moment to its last.
Every point has `<ele>` and `<time>`, with milliseconds where needed. A point
filled in by `--check` names its source in `<src>`, and when the source had
them a point carries the measured speed in m/s and the course in degrees, as a
Garmin TrackPointExtension:

```xml
<trkpt lat="56.0352876" lon="13.2601768"><ele>329.9</ele><time>2026-10-17T10:00:27Z</time><src>fl02_42294bf5.gpx</src><extensions><gpxtpx:TrackPointExtension><gpxtpx:speed>50.42</gpxtpx:speed><gpxtpx:course>356.0</gpxtpx:course></gpxtpx:TrackPointExtension></extensions></trkpt>
```

The GPX always spans the whole clip. Where no track reaches the clip's first or
last moment, a point there holds the nearest position, with no speed or
course, so that OVRLEY shows the GPX as long as the video and the sync offset
stays 0. `--check` does not count it as data: the gap is still reported, and
filled on a later run if a track for it turns up.

```xml
<trkpt lat="56.0833277" lon="13.1939228"><ele>72.9</ele><time>2026-10-17T11:36:08Z</time><src>hold</src></trkpt>
```

## Language

Messages are English or Swedish: `--lang sv`, or set `GOPRO_LANG=sv` once for
all the tools (`export GOPRO_LANG=sv` in bash, `$env:GOPRO_LANG = "sv"` in
PowerShell), the same as in gopro-max-gpx-pipeline and 360-cli-tools.

## Testing

```bash
cd ~/dev/trim-gpx
python3 -m unittest discover -s tests -v
```

The tests need neither network nor ffmpeg: a synthetic flight, shaped like a
Flightradar24 export, is "flown" by a camera that writes gopro-telemetry-style
GPX at 10 Hz and by a SkyDemon-style logger, and stubs stand in for ffprobe and
gpsbabel.

- `tests/test_check.py` covers `--check`: a complete clip left alone, gaps at
  the start, in the middle and at the end, a clip with no fix that takes its
  altitude from its neighbours, SkyDemon offered before Flightradar24, the
  placeholder, a camera clock on local time, answers typed at the prompt, a
  whole folder, a re-run and `--refill`, and a missing video. A start that
  stays missing is held so that the GPX spans the clip, is still reported on a
  re-run, is added to a 1.2.0 GPX that lacks it, and gives way to a track that
  covers it. Also saving the
  Flightradar24 exports as GPX: once, from the CSV, again when the export is
  newer, never over a GPX gpsbabel did not make, not with `--dry-run`, only a
  warning when gpsbabel is missing or fails. With gpsbabel installed, one test
  runs the real one on a KML and a CSV and checks that every point keeps its
  time, position, altitude, speed and course.
- `tests/test_trim_gpx.py` covers cutting: the exact window, measured speed and
  course, a course through north, resampling, time zones, GoPro chapters, error
  messages and both languages. The KML, CSV and gpsbabel GPX of the same flight
  must give byte-identical output, and the track is saved as GPX but never
  over the OUTPUT. A track that covers only part of the clip is held out to its
  ends.

Also checked on real data. On a real clip whose camera waited 63 s for a fix,
`--check` filled the gap from a Flightradar24 export with the altitude and
position lined up at the seam (no step in altitude, no jump in speed). One
flight exported from Flightradar24 as both KML and CSV gave byte-identical GPX
from either file, and gpsbabel's GPX of the KML gave the same file again. A
SkyDemon log was read with its speed. OVRLEY's own GPX parser
(`app/src/lib/activity/gpx-parser.js`, OVRLEY commit `13c3f41`), run in
Chromium, read the measured speed and course from every filled point.

## Related

- [360-cli-tools](https://github.com/zekesixniner/360-cli-tools): `xfade_concat.py` and `titles_in_360.py`, which join the `_ovr` clips into the film
- [gopro-max-gpx-pipeline](https://github.com/zekesixniner/gopro-max-gpx-pipeline): one merged video with telemetry as SRT
- [gopro-telemetry-tool](https://github.com/zekesixniner/gopro-telemetry-tool): the camera's own GPX from the `.360`
- [inject360-inplace](https://github.com/zekesixniner/inject360-inplace): spherical metadata, always the last step

## License

MIT, see [LICENSE](LICENSE).
