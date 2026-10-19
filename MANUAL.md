# Manual: rebuilding a clip's GPS track from Flightradar24

🇸🇪 [Svenska](MANUAL.sv.md) · [Back to the README](README.md)

Now and then the GoPro MAX2 records a clip without a GPS fix. It was switched
on just before, or it sat too deep in the cockpit to see the sky. The telemetry
extracted from that `.360` then has no positions, and OVRLEY has nothing to draw
for the clip: no map, no speed, no altitude.

If Flightradar24 tracked the flight, its track can stand in for the camera's
GPS. This manual goes from the empty GPX to the clip in the finished film.

- [What you need](#what-you-need)
- [The pipeline](#the-pipeline)
- [1. Confirm that the clip has no GPS](#1-confirm-that-the-clip-has-no-gps)
- [2. Download the flight from Flightradar24](#2-download-the-flight-from-flightradar24)
- [3. Cut the track to the clip](#3-cut-the-track-to-the-clip)
- [4. Check the result against the video](#4-check-the-result-against-the-video)
- [5. If the window misses the track: the camera's clock](#5-if-the-window-misses-the-track-the-cameras-clock)
- [6. OVRLEY](#6-ovrley)
- [7. Back into the film](#7-back-into-the-film)
- [What a Flightradar24 track can and cannot tell](#what-a-flightradar24-track-can-and-cannot-tell)
- [Troubleshooting](#troubleshooting)
- [An example: GS010132, 17 October 2026](#an-example-gs010132-17-october-2026)

## What you need

**Flightradar24 must have tracked the flight with positions.**

- The aircraft's transponder must be on and sending **ADS-B**: Mode S extended
  squitter with a GNSS position source. That is where Flightradar24's positions,
  speed and heading come from.
- Without ADS-B, Flightradar24 can only place an aircraft by MLAT, timing its
  transponder replies at three or more receivers. In most of Europe that works
  above roughly 5,000–10,000 ft
  ([Flightradar24](https://www.flightradar24.com/how-it-works/mlat)), so for a
  VFR flight a few thousand feet up, no ADS-B means no track.
- A receiver must hear the aircraft. Low down and on the ground the coverage
  has holes; trim-gpx shows the largest gap so you can see them. A receiver of
  your own near the home field helps.

**You must be able to download the flight.** Flightradar24's KML and CSV export
is for Silver, Gold and Business subscribers, with 90 days, one year and three
years of history
([Flightradar24](https://www.flightradar24.com/blog/inside-flightradar24/using-the-new-flightradar24-kml-and-csv-export-tools/)).
Hosting a Flightradar24 receiver gives you the free Contributor Plan, which is
what the maintainer downloads with. Download the flight while it is still
within your plan's history.

**The camera's clock should be right** to within a few seconds. Which time zone
it writes is checked in [step 5](#5-if-the-window-misses-the-track-the-cameras-clock).

**Tools:** `trim_gpx.py` ([installation](README.md#installation)), ffprobe
(`sudo apt install ffmpeg` in WSL), and OVRLEY.

## The pipeline

```
 camera                            Flightradar24
 GS010132.360                      fl03_4229ad6f.kml (or .csv)
   creation_time, length             time, position, altitude, speed, course
        │                                  │
        └────────────────┬─────────────────┘
                         ▼
        trim_gpx.py --video GS010132.360                    WSL
                         │
                         ▼
        fl03_4229ad6f_GS010132.gpx    exactly the clip's 62.208 s
                         │
 GoPro Player            │
 GS010132.mp4 ──────────►┤
                         ▼
        OVRLEY (MP4 + GPX) ──► GS010132_ovr.mp4                 Windows
                         │
                         ▼
        xfade_concat.py → titles_in_360.py → inject360-inplace (last)
```

## 1. Confirm that the clip has no GPS

Extract the telemetry as usual (gopro-telemetry-tool or gpmf2gpx.py). A clip
recorded without a fix gives a GPX with no points:

```bash
grep -c '<trkpt' GS010132.gpx
0
```

If the GPS drops out for only part of the clip, keep the camera's own track:
OVRLEY interpolates across a short dropout. Use the Flightradar24 track for the
whole clip when the gap is too long for that.

## 2. Download the flight from Flightradar24

1. Log in at flightradar24.com and search for the aircraft's registration.
2. On the aircraft's page, find the flight in the list of past flights.
3. Press **KML** (or **CSV**) for that flight.

Name the file after your flight and keep Flightradar24's flight ID, e.g.
`fl03_4229ad6f.kml`: flight 3 of the day, Flightradar24 flight `4229ad6f`.

**KML or CSV?** Either. Both hold time, position, altitude, ground speed and
heading for every point, and trim-gpx makes the same GPX from both. The KML can
also be opened in Google Earth to look at the flight.

No conversion is needed: trim-gpx reads the export as it is. If you have
already converted it with gpsbabel, that file works too. gpsbabel keeps
Flightradar24's speed and heading as text in each point's `<desc>`, and
trim-gpx reads them from there.

## 3. Cut the track to the clip

Point `--video` at the camera's original file. trim-gpx reads its
`creation_time` and length with ffprobe:

```bash
cd /path/to/the/flight
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

Use the camera's `.360`, from the card or your copy of it: its `creation_time`
is the camera's own record of when the recording started.

Without `--video`, read the same two values yourself and give them as
`--start` and `--duration`:

```bash
ffprobe -v error -show_entries format=duration:format_tags=creation_time -of default=nw=1 GS010132.360
duration=62.208000
TAG:creation_time=2026-10-17T12:05:07.000000Z

trim_gpx.py fl03_4229ad6f.kml fl03_4229ad6f_GS010132.gpx --start 2026-10-17T12:05:07Z --duration 62.208
```

**Chapters.** A long recording is split into chapters: `GS010068`, `GS020068`,
`GS030068` and so on. For chapter 2 onwards, `--video` checks whether the
chapter's `creation_time` is its own start or the start of the whole
recording, by comparing it with chapter 1. If it is the recording's, the
earlier chapters' lengths are added, and the output says so:

```
Video:    GS030068.360: creation_time 2026-10-17T12:00:00Z, length 4 s
          chapter 3 of recording 0068: its creation_time is the recording's start, adding the 2 earlier chapter(s) (18 s)
```

That needs all the recording's chapters in the same folder. A chapter on its
own gives a warning instead. Without `--video`, do the same sum by hand.

## 4. Check the result against the video

The summary is there to be compared with the picture.

- **Window.** No `[WARNING]` or `[ERROR]` means the whole clip lies inside the track.
- **Largest gap.** Flightradar24 delivers a point every few seconds, so a gap of
  a few seconds is normal. Tens of seconds is a hole in the coverage, crossed by
  a straight line.
- **Altitude, speed and course** at the start and end of the clip.
  `Course: 060° → 189°` is a right turn of some 130°: does the video show one?
  A climb, a turn onto final or the runway heading on take-off are all easy to
  check.
- The GPX can also be opened in Google Earth, GPXSee or similar, to see that the
  track is where you flew.

## 5. If the window misses the track: the camera's clock

`creation_time` is the camera's clock, and the file always marks it as UTC
(`Z`), whatever the clock was set to. If it was set to local time, the window
lands one or two hours off, outside the flight, and trim-gpx says which offset
fits:

```
Window:   2026-10-17 10:05:07Z – 10:06:09Z (62.208 s)
[ERROR]   The window lies entirely outside the track.
          Without --tz the window lands at 12:05:07Z – 12:06:09Z, fully inside the track.
```

Here `--tz 2` had been given, but the camera writes UTC. `--tz 2` means "the
start time is Swedish summer time" (UTC+2), `--tz 1` winter time. The MAX2
this was developed with writes UTC, checked against Flightradar24, so it needs
no `--tz`. Check your own camera once against a flight.

A wrong time zone is caught only when the other time falls outside the flight.
On a flight long enough to cover both times, compare the summary with the video
before trusting the result.

A clock a few seconds off shows as an overlay slightly ahead of or behind the
picture; at 100 kt one second is about 50 m. Adjust that in OVRLEY
([step 6](#6-ovrley)), or move `--start`.

## 6. OVRLEY

1. Import the stitched clip, GoPro Player's MP4 (e.g. `GS010132.mp4`), and the
   GPX as the activity.
2. **Sync.** OVRLEY's automatic sync compares the video's creation time with the
   GPX, trying it both as local time and as UTC. With a GPX cut exactly to the
   clip it lands on a sync offset of 0 s. If OVRLEY says *Video could not be
   synced with activity*, for example because the MP4 has lost its creation
   time, set the sync offset to 0 by hand: the GPX starts on the clip's first
   frame.
3. **Fine-tune** if a turn in the picture and on the map do not line up: the
   sync offset can be nudged a second at a time.
4. Lay out the widgets and render as for the other clips: `GS010132_ovr.mp4`.

The speed widget shows Flightradar24's measured ground speed. OVRLEY's GPX
import reads it from each point and uses it instead of computing speed from the
positions (checked against OVRLEY's source, commit `13c3f41`).

OVRLEY's NVIDIA path writes 8-bit video, also from GoPro Player's 10-bit
export, so `GS010132_ovr.mp4` matches the other `_ovr` clips. Do not put the
10-bit export itself into the same `xfade_concat.py` run: it fails at the first
transition with `Invalid output format nv12 for hwframe download`.

## 7. Back into the film

Join as usual, with the new clip in its place:

```powershell
python $HOME\bin\xfade_concat.py -o GS00131-134_ovr.mp4 GS010131_ovr.mp4 GS010132_ovr.mp4 GS010133_ovr.mp4 GS010134_ovr.mp4
```

Then `titles_in_360.py`, and `inject360-inplace` last.

### With gopro-max-gpx-pipeline instead

If you make one merged video with the telemetry as SRT
([gopro-max-gpx-pipeline](https://github.com/zekesixniner/gopro-max-gpx-pipeline)),
put the cut GPX in place of the clip's empty one, under the same name, before
`gpx_to_dji_srt.py`:

```bash
mv GS010132.gpx GS010132.gpx.empty
cp fl03_4229ad6f_GS010132.gpx GS010132.gpx
gpx_to_dji_srt.py telemetry.srt --pairs-from-basenames 'GS0*.gpx' --video-dir .
```

Position, altitude and clock then come through for that clip. The SRT carries
no speed, though, so OVRLEY computes it from the positions, and with
Flightradar24's whole-second timestamps it jumps about. The per-clip way above
avoids that.

## What a Flightradar24 track can and cannot tell

| | camera GPS | Flightradar24 through trim-gpx |
|---|---|---|
| position | several times a second | a point every few seconds, straight lines in between: a tight turn is cut a little |
| time | GPS time | whole seconds |
| speed | from the GPS | measured ground speed (ADS-B), whole knots |
| course | from the GPS | measured track, whole degrees |
| altitude | GPS altitude | barometric, see below |

**Altitude** is the transponder's barometric altitude, referenced to 1013 hPa
and not corrected for the day's QNH
([Flightradar24](https://www.flightradar24.com/blog/inside-flightradar24/understanding-altitude-on-flightradar24/)),
and many light-aircraft transponders report it in 100 ft steps. On the ground
Flightradar24 reports 0. The altitude in the rebuilt clip can therefore differ
from the camera's GPS altitude in the clips before and after, by about 30 ft
for every hPa the day's QNH differs from 1013.

**On the ground and at low level** the coverage often stops, so taxiing and the
start of the take-off roll may be missing. A clip that starts before
Flightradar24 picks the aircraft up gives a `[WARNING]`, and the GPX covers only
the part that was tracked.

**Speed in other tools.** OVRLEY's GPX import reads the measured speed. A tool
that computes speed from the positions sees the whole-second steps instead.

## Troubleshooting

| you see | why | do |
|---|---|---|
| `[ERROR] The window lies entirely outside the track.` with a `--tz` suggestion | the camera's clock runs in another time zone than you gave | use the suggested `--tz` |
| `Neither --tz 0, 1 nor 2 puts the window inside the track` | wrong flight or date, or a camera clock far off | compare the date on the `Source:` line with the clip's; check the clock |
| `[WARNING] The track only covers …` | Flightradar24 did not track that part: on the ground, low down, at the edge of coverage | nothing to do; OVRLEY shows no data for the rest of the clip |
| `Speed: … (derived from the positions)` | the input had no measured speed | use Flightradar24's KML or CSV |
| `[WARNING] … is chapter N of a recording, but the earlier chapters are not next to it` | a chapter file without chapter 1 beside it | put the recording's chapters in one folder, or add the earlier chapters' length to `--start` |
| `… has no creation_time` | not the camera's original file | use the `.360`, or give `--start` |
| `ffprobe not found` | ffmpeg is not installed | `sudo apt install ffmpeg`, or give `--start` and `--duration` |
| `Could not read …: line N: …` | a damaged or different CSV | check that line; the header must have a time column and a position column |
| OVRLEY: *Video could not be synced with activity* | the MP4's creation time is missing or different | set the sync offset to 0 |

## An example: GS010132, 17 October 2026

The MAX2 got no fix for `GS010132`, 62 seconds between two clips that did have
GPS. Flightradar24 had the flight: 1,526 points from 11:36:47Z to 12:35:00Z.

The first attempt used `--tz 2`, on the assumption that the camera ran on
Swedish time. The window landed at 10:05Z, an hour and a half before take-off.
Without `--tz` it landed at 12:05:07–12:06:09Z, in the middle of the flight:
29 points at most 3 s apart, 700–900 ft, a right turn from 060° to 189°, and a
ground speed rising from 91 to 125 kt.

Computed from the positions, the speed would have jumped between 62 and 166 kt.
With Flightradar24's measured speed in the file, OVRLEY's GPX import reads 91 to
125 kt.
