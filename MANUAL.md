# Manual: complete a clip's GPS track

🇸🇪 [Svenska](MANUAL.sv.md) · [Back to the README](README.md)

Now and then the GoPro MAX2 records without a GPS fix for part of a clip, or
for all of it. It was switched on just before, or it sat too deep in the
cockpit to see the sky. The telemetry extracted from that `.360` then lacks
positions, and OVRLEY has nothing to draw: the overlay stands still, or shows
nothing at all.

The camera's own track is the best data there is, ten points a second, so
`trim_gpx.py --check` keeps it wherever it exists and fills only the gaps: from
a SkyDemon log of the flight if you have one, otherwise from Flightradar24.

- [What you need](#what-you-need)
- [The pipeline](#the-pipeline)
- [1. Extract the camera's GPX as usual](#1-extract-the-cameras-gpx-as-usual)
- [2. Put the flight's tracks next to them](#2-put-the-flights-tracks-next-to-them)
- [3. Run the check](#3-run-the-check)
- [4. Fill the gaps](#4-fill-the-gaps)
- [5. Check the result](#5-check-the-result)
- [6. OVRLEY](#6-ovrley)
- [7. Back into the film](#7-back-into-the-film)
- [Cutting a track by hand](#cutting-a-track-by-hand)
- [The camera's clock](#the-cameras-clock)
- [What the filled data can and cannot tell](#what-the-filled-data-can-and-cannot-tell)
- [Troubleshooting](#troubleshooting)
- [Two examples from 17 October 2026](#two-examples-from-17-october-2026)

## What you need

**Tools:** `trim_gpx.py` ([installation](README.md#installation)), ffprobe
(`sudo apt install ffmpeg` in WSL), gopro-telemetry-tool for the camera's GPX,
and OVRLEY. The clips' `.360` files must be at hand, on the card or a copy:
their `creation_time` and length say what each GPX should cover.

**A track of the flight to fill from**, in this order of preference:

1. **SkyDemon.** If SkyDemon recorded the flight, export its log as GPX. It has
   the tablet's GPS altitude and measured ground speed, with a point every few
   seconds (every 5 s in the log this was developed with).
2. **Flightradar24.** It works only if Flightradar24 tracked the flight with
   positions:
   - The aircraft's transponder must be on and sending **ADS-B**: Mode S
     extended squitter with a GNSS position source. That is where
     Flightradar24's positions, speed and heading come from.
   - Without ADS-B, Flightradar24 can only place an aircraft by MLAT, timing
     its transponder replies at three or more receivers. In most of Europe that
     works above roughly 5,000–10,000 ft
     ([Flightradar24](https://www.flightradar24.com/how-it-works/mlat)), so for
     a VFR flight a few thousand feet up, no ADS-B means no track.
   - A receiver must hear the aircraft. Low down and on the ground the coverage
     has holes. A receiver of your own near the home field helps.
   - You must be able to download the flight. KML and CSV export is for
     Silver, Gold and Business subscribers, with 90 days, one year and three
     years of history
     ([Flightradar24](https://www.flightradar24.com/blog/inside-flightradar24/using-the-new-flightradar24-kml-and-csv-export-tools/)).
     Hosting a Flightradar24 receiver gives you the free Contributor Plan,
     which is what the maintainer downloads with. Download the flight while it
     is still within your plan's history.

**The camera's clock should be right** to within a few seconds. `--check`
tells you how far off it is, for every clip with a fix
([the camera's clock](#the-cameras-clock)).

## The pipeline

```
 camera  GS010130.360 ──gopro-telemetry-tool──► GS010130.gpx  (the camera's own GPS)
                                                     │
 SkyDemon log (GPX) ─────────┐                       │
 Flightradar24 (KML or CSV) ─┴─► trim_gpx.py --check .  ◄── creation_time, length (.360)
                                                     │
                                                     ▼
                      GS010130.gpx, complete (the original kept as GS010130.gpx.orig)
                                                     │
 GoPro Player  GS010130.mp4 ────────────────────────►┤
                                                     ▼
                        OVRLEY (MP4 + GPX) ──► GS010130_ovr.mp4
                                                     │
              xfade_concat.py → titles_in_360.py → inject360-inplace (last)
```

## 1. Extract the camera's GPX as usual

Extract the telemetry with gopro-telemetry-tool into the flight's folder: one
`GS010130.gpx` per clip. Nothing changes here; `--check` works on these files.

## 2. Put the flight's tracks next to them

Put the SkyDemon log and/or the Flightradar24 export of the flight in the same
folder. `--check` looks there for tracks that cover what is missing. (A track
kept elsewhere can be named with `--fill`, or its folder with `--search`.)

**From Flightradar24:** log in at flightradar24.com and search for the
aircraft's registration. On the aircraft's page, find the flight in the list of
past flights and press **KML** (or **CSV**). Name the file after your flight
and keep Flightradar24's flight ID, e.g. `fl02_42294bf5.kml`: flight 2 of the
day, Flightradar24 flight `42294bf5`. KML and CSV give the same result, and a
gpsbabel conversion of the KML works too. Several of them in the folder are
offered once.

**From SkyDemon:** export the flight's log as GPX, e.g. `SD_ESTT-ESTL.gpx`.
SkyDemon names itself in the file, and that is how it is recognised.

## 3. Run the check

```bash
cd /path/to/the/flight
trim_gpx.py --check . --video-dir /mnt/e/DCIM/100GOPRO
```

`--video-dir` says where the clips' `.360` files are. Without it they are
looked for next to the GPX. If only an `.mp4` is found there, it is used with
a warning: its `creation_time` is only right if it is the camera's.

Each clip gets a line:

```
Checking 2 clip(s), videos in /mnt/e/DCIM/100GOPRO:
  GS010130.gpx  missing   63.1 s of 203.093 s: 10:00:27Z – 10:01:30Z · camera clock +0.03 s
  GS010132.gpx  no GPS    62.208 s
```

- **complete**: the camera has data for the whole clip; the file is left alone.
- **missing**: stretches without data, longer than 2 s (`--max-gap`).
- **no GPS**: the camera had no fix at all during the clip.
- **error**: the clip could not be checked, e.g. no `.360` was found.
- **camera clock**: GPS time at the clip's first frame minus its
  `creation_time`. Since `creation_time` is in whole seconds, anything under a
  second means the clock is right.

`--dry-run` stops here and changes nothing.

## 4. Fill the gaps

For each clip with gaps, `--check` offers the tracks that cover them, a
SkyDemon log before a Flightradar24 track:

```
GS010130.gpx: missing 10:00:27Z – 10:01:30Z (63.1 s of 203.093 s)
  Fill from:
    1  fl02_42294bf5.gpx  Flightradar24  covers 63.1 s of 63.1 s
  Choose 1–1 (Enter = 1), another file, or n to leave the gap:
  ✓ 63.1 s from fl02_42294bf5.gpx (30 points); matched to the camera: altitude +182 ft, position 3 m
  ✅ GS010130.gpx updated: 1401 camera points + 30 filled (original: GS010130.gpx.orig)
```

Press Enter for the first, give the number of another, or type the path of a
file it did not find (a Windows path such as `C:\Users\…\log.gpx` works in WSL).
`n` leaves the gap. If one track covers only part of a gap, it asks again for
the rest.

`--yes` takes the best track without asking, and `--fill TRACK` names the track
yourself, also when nothing is asked (in a script, say).

What happens to the file:

- **The camera's points stay as they are.** Only the missing stretches are
  filled, and each filled point names its source in `<src>`.
- **The fill is lined up with the camera.** At each seam it is moved to meet the
  camera's position and GPS altitude, measured over the 10 seconds of camera
  data beside the seam, so there is no step in altitude and no jump in speed.
  Here Flightradar24's barometric altitude was 182 ft below the camera's GPS.
- **A clip with no fix of its own** has no seam. It gets the altitude difference
  from the neighbouring clips' GPX in the same folder (up to 30 minutes away),
  so its altitude follows on from the clips before and after it in the film.
  Without neighbours the source's own altitude is used, and the output says so.
- **The file is updated in place**, so OVRLEY and gopro-max-gpx-pipeline find it
  under the usual name. The camera's original is kept as `GS010130.gpx.orig`.
  `-o` writes elsewhere instead.
- **Measured speed and course** from the source go into each filled point, and
  OVRLEY shows them instead of computing speed from positions.

## 5. Check the result

Run the check again. A filled clip now counts as complete and says where the
fill came from:

```
  GS010130.gpx  complete  203.093 s, largest gap 3.0 s; 63.1 s filled earlier from fl02_42294bf5.gpx
  GS010132.gpx  complete  62.208 s, largest gap 3.0 s; 62.2 s filled earlier from fl03_4229ad6f.kml
```

Each clip was filled from its own flight's export: only tracks that cover the
missing time are offered.

The GPX can be opened in Google Earth, GPXSee or similar, and the filled
stretch compared with the video: a turn, a climb, the runway on landing.

To fill again from another track: `--refill` throws away the earlier fill and
keeps the camera's points. To go back to the camera's original:
`mv GS010130.gpx.orig GS010130.gpx`.

## 6. OVRLEY

1. Import the stitched clip, GoPro Player's MP4 (e.g. `GS010130.mp4`), and its
   GPX as the activity, as for any other clip.
2. **Sync.** OVRLEY's automatic sync compares the video's creation time with
   the GPX. The completed GPX starts on the clip's first frame, so the sync
   offset lands on 0 s. If OVRLEY says *Video could not be synced with
   activity*, set the sync offset to 0 by hand.
3. Fine-tune if a turn in the picture and on the map do not line up: the sync
   offset can be nudged a second at a time.
4. Render as for the other clips: `GS010130_ovr.mp4`.

OVRLEY's GPX import reads the measured speed from each filled point and uses it
instead of computing speed from the positions (checked against OVRLEY's source,
commit `13c3f41`). Its NVIDIA path writes 8-bit video, also from GoPro Player's
10-bit export, so the `_ovr` clips match each other. Do not put a 10-bit export
itself into the same `xfade_concat.py` run as `_ovr` clips: it fails at the
first transition with `Invalid output format nv12 for hwframe download`.

## 7. Back into the film

```powershell
python $HOME\bin\xfade_concat.py -o GS00131-134_ovr.mp4 GS010131_ovr.mp4 GS010132_ovr.mp4 GS010133_ovr.mp4 GS010134_ovr.mp4
```

Then `titles_in_360.py`, and `inject360-inplace` last.

**With gopro-max-gpx-pipeline instead** (one merged video, telemetry as SRT):
the completed GPX keeps its name, so `gpx_to_dji_srt.py --pairs-from-basenames
'GS0*.gpx'` picks it up. The SRT carries no speed, though, so OVRLEY computes
it from the positions there, and over a Flightradar24 stretch it jumps about
with the whole-second timestamps. The per-clip way above avoids that.

## Cutting a track by hand

When there is no camera GPX at all, a track can be cut to a clip directly:

```bash
trim_gpx.py fl03_4229ad6f.kml GS010132.gpx --video /mnt/e/DCIM/100GOPRO/GS010132.360
```

```
Source:   1526 timestamped points, 2026-10-17 11:36:47Z – 12:35:00Z
Video:    GS010132.360: creation_time 2026-10-17T12:05:07Z, length 62.208 s
Window:   2026-10-17 12:05:07Z – 12:06:09Z (62.208 s)
In window: 29 source points, largest gap between points 3 s
Altitude: 213–274 m (700–900 ft)
Speed:    91–125 kt (measured in the source, written to the GPX)
Course:   060° → 189°

✅ Saved 30 points → GS010132.gpx
```

Without `--video`, give `--start` and `--duration` (from `ffprobe -v error
-show_entries format=duration:format_tags=creation_time -of default=nw=1
GS010132.360`). For chapter 2 onwards of a long recording, `--video` checks
whether the chapter's `creation_time` is its own start or the whole recording's
(by comparing with chapter 1 in the same folder) and adds the earlier chapters'
length when needed. A cut track carries no altitude matching: that needs
`--check` and the camera's GPX, even an empty one.

## The camera's clock

`creation_time` is the camera's clock, and the file always marks it as UTC
(`Z`), whatever the clock was set to. gopro-telemetry's first GPX point is
dated to the clip's first frame in GPS time, so for every clip with a fix
`--check` can compare the two: that is the `camera clock` column. The MAX2 this
was developed with writes UTC and is right to within the second that
`creation_time` resolves.

A camera on local time shows up as a clock one or two hours off. For a clip
with a fix the window then follows GPS time, with a warning (set OVRLEY's sync
offset to 0 for that clip). A clip without a fix cannot be checked that way:
give `--tz 2` for Swedish summer time, `--tz 1` for winter time. When cutting a
track by hand, a window that misses the track gets a suggestion:

```
Window:   2026-10-17 10:05:07Z – 10:06:09Z (62.208 s)
[ERROR]   The window lies entirely outside the track.
          Without --tz the window lands at 12:05:07Z – 12:06:09Z, fully inside the track.
```

A clock a few seconds off shows as an overlay slightly ahead of or behind the
picture; at 100 kt one second is about 50 m. Adjust that in OVRLEY.

## What the filled data can and cannot tell

| | camera GPS | SkyDemon | Flightradar24 |
|---|---|---|---|
| position | 10 times a second | a point every few seconds | a point every few seconds |
| time | GPS time | whole seconds | whole seconds |
| speed | from the GPS | measured, m/s | measured ground speed (ADS-B), whole knots |
| course | from the GPS | — (OVRLEY computes it) | measured track, whole degrees |
| altitude | GPS | GPS | barometric, see below |

Between points, the filled track runs in straight lines, so a tight turn is cut
a little.

**Flightradar24's altitude** is the transponder's barometric altitude,
referenced to 1013 hPa and not corrected for the day's QNH
([Flightradar24](https://www.flightradar24.com/blog/inside-flightradar24/understanding-altitude-on-flightradar24/)),
and many light-aircraft transponders report it in 100 ft steps. On the ground
Flightradar24 reports 0. `--check` moves it to the camera's GPS altitude at the
seams; a cut track keeps it as it is.

**On the ground and at low level** Flightradar24's coverage often stops, so
taxiing and the start of the take-off roll may be missing. What no track covers
stays missing, and `--check` says so.

## Troubleshooting

| you see | why | do |
|---|---|---|
| `missing` with nothing offered | no track next to the clips covers the gap | put the SkyDemon log or Flightradar24 export in the folder, or name it with `--fill` |
| `… has no data for the missing time.` | the track chosen is from another flight or time | choose another, or check the date and the clip's `--video-dir` |
| `still missing: …` | the tracks only cover part of the gap (ground, low level, edge of coverage) | add another track, or `n` to leave it |
| `altitude not matched` | a clip with no fix and no neighbouring camera GPX in the folder | put the neighbouring clips' GPX in the folder and run with `--refill` |
| `error  no video GS010130.360 or .mp4` | the `.360` was not found | give `--video-dir` |
| `[WARNING] … timed by GS010130.mp4, not the camera's .360` | only an `.mp4` was found | give `--video-dir` with the `.360` files |
| `[WARNING] … the camera clock is … off GPS time` | the camera's clock was wrong (or on local time) | nothing for the GPX; set OVRLEY's sync offset to 0 |
| `ffprobe not found` | ffmpeg is not installed | `sudo apt install ffmpeg` |
| cutting: `[ERROR] The window lies entirely outside the track.` with a `--tz` suggestion | the camera's clock runs in another time zone than you gave | use the suggested `--tz` |
| cutting: `Could not read …: line N: …` | a damaged or different CSV | check that line; the header must have a time column and a position column |
| OVRLEY: *Video could not be synced with activity* | the MP4's creation time is missing or different | set the sync offset to 0 |

## Two examples from 17 October 2026

**GS010130: the camera waited a minute for a fix.** The clip runs from
10:00:27 to 10:03:50Z, the approach and landing, but the camera's GPS starts
only at 10:01:30. gopro-telemetry's placeholder for the first frame sat at the
first fix's position, so OVRLEY stood still for 63 seconds. The placeholder
also showed the camera clock to be right: 10:00:27.026 in GPS time against a
`creation_time` of 10:00:27 (whole seconds). `--check` filled the 63 s from the Flightradar24
export of the flight (30 points). Beside the seam the camera's GPS altitude
was 182 ft above Flightradar24's barometric one and the positions agreed to
within 3 m, so the fill was moved by that much: the altitude runs 905, 911,
914 ft across the seam, and the speed computed from the positions 76, 75 kt.

**GS010132: no fix at all.** The camera's GPX was empty. `--check` filled the
whole 62 s from the Flightradar24 export. With the GPX of the clips before and
after it in the same folder, the altitude is matched to their GPS altitude;
without them it is Flightradar24's barometric altitude, and the output says so.
