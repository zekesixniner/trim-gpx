# trim-gpx

Cuts a GPX, KML or CSV track down to exactly one video clip. Made for the day
the GoPro records a clip **without a GPS fix**: the aircraft's track from
[Flightradar24](https://www.flightradar24.com) stands in for the camera's GPS,
and the result goes into [OVRLEY](https://www.ovrley.cc) like any other clip's
telemetry.

🇸🇪 [Svensk version av denna README](README.sv.md) ·
📖 [Manual: rebuilding a clip's GPS from Flightradar24](MANUAL.md) / [Manual på svenska](MANUAL.sv.md)

```bash
trim_gpx.py fl03_4229ad6f.kml fl03_4229ad6f_GS010132.gpx --video /mnt/e/DCIM/100GOPRO/GS010132.360
```

```
Source:   1526 timestamped points, 2026-10-17 11:36:47Z – 12:35:00Z
Video:    GS010132.360: creation_time 2026-10-17T12:05:07Z, length 62.208 s
Window:   2026-10-17 12:05:07Z – 12:06:09Z (62.208 s)
In window: 29 source points, largest gap between points 3 s
Altitude: 213–274 m (700–900 ft)
Speed:    91–125 kt (measured in the source, written to the GPX)
Course:   060° → 189°

✅ Saved 30 points → fl03_4229ad6f_GS010132.gpx
```

## What it does

- **Reads Flightradar24's exports as they are**, KML or CSV, as well as any
  GPX 1.0/1.1 or KML with timestamps. gpsbabel's conversion of a
  Flightradar24 KML works too.
- **Cuts exactly.** The first and last point are interpolated, so the track
  starts at the clip's first moment and ends at its last, to the millisecond.
- **Takes the window from the clip.** `--video` reads the clip's
  `creation_time` and length with ffprobe, including chapter 2, 3 … of a long
  GoPro recording.
- **Keeps the measured speed and course.** Flightradar24's timestamps are
  whole seconds while its points come every two to three seconds, so a speed
  computed from the positions jumps about: 62–166 kt in the example above,
  where the aircraft flew 91–125 kt. trim-gpx writes Flightradar24's measured
  ground speed and course into every point, and OVRLEY uses that speed instead
  of computing its own.
- **Catches a wrong time zone.** If the window misses the track, it says which
  `--tz` would put it inside.
- **Prints a summary** (points, largest gap, altitude, speed, course) to check
  against the video.
- Python standard library only.

## Requirements

- Python 3.9 or newer
- ffprobe, part of ffmpeg, for `--video` (`sudo apt install ffmpeg` in WSL/Ubuntu)
- A track of the flight. From Flightradar24 that takes an account that can
  export KML/CSV and an aircraft that sends ADS-B — see
  [what you need](MANUAL.md#what-you-need) in the manual.

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
trim_gpx.py INPUT OUTPUT --video CLIP                [--tz H] [--hz N] [--lang sv]
trim_gpx.py INPUT OUTPUT --start TIME --duration LEN [--tz H] [--hz N] [--lang sv]
```

| option | |
|---|---|
| `INPUT` | the track: Flightradar24 KML or CSV, or any GPX/KML with times |
| `OUTPUT` | the GPX 1.1 file to write |
| `--video CLIP` | take start and length from the clip: its `creation_time` and duration, read with ffprobe. Use the camera's original file, e.g. `GS010132.360` |
| `--start TIME` | clip start: `12:05:07` (the date is taken from the track), `2026-10-17T12:05:07Z`, ffprobe's `2026-10-17T12:05:07.000000Z` or exiftool's `2026:10:17 12:05:07`. A time without a zone is UTC. Overrides `--video` |
| `--duration LEN` | clip length: `62.208` (seconds) or `1:02`. Overrides `--video` |
| `--tz H` | the start time is the camera's local clock, UTC+H: `2` for Swedish summer time, `1` for winter time. Default `0`, the camera runs on UTC |
| `--hz N` | resample to N points per second. OVRLEY does not need it |
| `--ffprobe PATH` | the ffprobe to use (default: `ffprobe` on PATH) |
| `--lang en\|sv` | message language (default: `$GOPRO_LANG`, else English) |
| `--version` | print the version |

Exit status: `0` done (also when the track covers only part of the clip, with
a warning), `1` error, `2` the window lies entirely outside the track.

### Input formats

| source | what is read |
|---|---|
| Flightradar24 KML | the Trail placemarks: time, position and altitude; speed and heading from each point's description |
| Flightradar24 CSV | `Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction`, altitude in feet and speed in knots |
| gpsbabel's GPX of a Flightradar24 KML | the timed `<wpt>`; speed and heading from the description gpsbabel keeps in `<desc>` |
| any GPX 1.0/1.1 | timed `<trkpt>`, `<wpt>` and `<rtept>`; `<speed>` and `<course>` when present |
| other KML | `Placemark` with `TimeStamp`, and `gx:Track` |

Points without a time are skipped; Flightradar24's Route line has none.

### Output

A GPX 1.1 track with one segment. Every point has `<ele>` and `<time>`, with
milliseconds where needed. When the source had them, every point also carries
the measured speed in m/s and the course in degrees, as a Garmin
TrackPointExtension:

```xml
<trkpt lat="56.1582910" lon="13.2884790"><ele>213.4</ele><time>2026-10-17T12:05:07Z</time><extensions><gpxtpx:TrackPointExtension><gpxtpx:speed>47.33</gpxtpx:speed><gpxtpx:course>60.0</gpxtpx:course></gpxtpx:TrackPointExtension></extensions></trkpt>
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

The tests run a synthetic flight shaped like a Flightradar24 export, with a
stub in place of ffprobe, so they need neither network nor ffmpeg. They cover
the exact window, the measured speed and course, a course interpolated through
north, resampling, time zones and the `--tz` hint, a window partly outside the
track, GoPro chapters, the error messages and both languages. The KML, the CSV
and gpsbabel's GPX of the same flight must give byte-identical output.

Also checked on real data. One flight exported from Flightradar24 as both KML
and CSV (1,526 points) gave byte-identical GPX from either file in 60 random
windows, and gpsbabel's GPX of the KML gave the same file again. OVRLEY's own
GPX parser (`app/src/lib/activity/gpx-parser.js`, OVRLEY commit `13c3f41`),
run in Chromium, read the speed and course from every point.

## Related

- [360-cli-tools](https://github.com/zekesixniner/360-cli-tools): `xfade_concat.py` and `titles_in_360.py`, which join the `_ovr` clips into the film
- [gopro-max-gpx-pipeline](https://github.com/zekesixniner/gopro-max-gpx-pipeline): one merged video with telemetry as SRT
- [gopro-telemetry-tool](https://github.com/zekesixniner/gopro-telemetry-tool): the camera's own GPX from the `.360`
- [inject360-inplace](https://github.com/zekesixniner/inject360-inplace): spherical metadata, always the last step

## License

MIT, see [LICENSE](LICENSE).
