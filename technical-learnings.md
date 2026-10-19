# Tekniska lärdomar — GoPro MAX2 videobearbetning

## Pipeline order

- Pipeline order är kritisk: kartöverlägg (`overlay_map.py`) → OVRLEY → `inject360-inplace` alltid sist, eftersom ffmpeg tar bort XMP spherical metadata vid remux

## GPU / ffmpeg-begränsningar och lösningar

- 10-bit overlay-begränsning: `overlay_cuda` stödjer inte 10-bit (`p010le`) på RTX 2080 Ti; lösningen är CPU-overlay + NVENC-encode med `format=yuv420p10le` på båda inputs och `format=yuv420p10` i filtret
- `hwdownload` kräver att dess `format`-option matchar NVDEC-hårdvarans native format (`nv12` för 8-bit, `p010le` för 10-bit) — att begära ett planart mål som `yuv420p` direkt misslyckas; konvertera i två steg, t.ex. `hwdownload,format=nv12,format=yuv420p`
- ffmpeg `filter_complex`-split: explicit `split=2` med namngivna outputs krävs för att undvika implicit felroutning av basframen i blur/overlay-filterkedjor

## GoPro-filformat och telemetri

- GoPro-kapitelfilssortering: `GSccnnnn` där `cc` = kapitel och `nnnn` = filnummer — måste sorteras på (filnummer, kapitel), inte alfabetiskt
- GPS9-format: GoPro MAX2 använder GPS9 (9 fält, 32 byte/punkt) med STMP-tidsstämplar; äldre verktyg som förväntar sig GPS5/GPSU är inkompatibla
- GPMF-extraktion: dynamisk stream-detektion via `ffprobe` som matchar codec tag `gpmd` är mer robust än hårdkodad `-map 0:3`; temp-filen måste ha `.mp4`-ändelse (inte `.bin`) för korrekt ffmpeg-muxer-val
- GPS-tidsstämpelinterpolering: använd faktisk förfluten tid till nästa klusters STMP-värde istället för en hårdkodad Hz-antagande, för att undvika burst-then-gap-kadensartefakter

## Telemetrisynk och GPX-giltighet

- DJI Format B SRT löser OVRLEY-telemetrisynkproblemet: elapsed timecode för framesynk plus riktig wall-clock-tid i `HOME(...)`-raden, vilket undviker problemet att en naivt sammanslagen GPX behåller verkliga pauser
- `<fix>`-sanering: `gopro-telemetry`s smooth-option ger flyttalsvärden i `<fix>`-element som misslyckas mot `gpxpy`s strikta schemavalidering; kräver en `re.sub`-sanerare

## Flightradar24 som GPS-ersättning för klipp utan satellitfix (2026-10-19)

- Verktyget är repot `trim-gpx` (`~/dev/trim-gpx`, `trim_gpx.py` 1.0.0, manual i `MANUAL.md`/`MANUAL.sv.md`). Kortaste vägen: `trim_gpx.py <fr24>.kml|.csv ut.gpx --video GS010132.360` (läser `creation_time` och längd med ffprobe; kapitel 2+ korrigeras när deras `creation_time` är hela inspelningens start)
- Kamerans klocka: GS010132:s `creation_time` (12:05:07Z) stämde med UTC mot FR24-spåret; `--tz 2` lade klippet 1,5 h före start. `trim_gpx.py` föreslår själv den `--tz` (0/1/2) som träffar spåret när fönstret missar
- FR24:s CSV-export (verifierad på riktig export): `Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction` — epoch, ISO-UTC, `"lat,lon"` i citattecken, höjd i fot, fart i knop, kurs i grader. KML och CSV av samma flygning ger identiska punkter och byte-identisk GPX
- gpsbabel 1.9.0 av en FR24-KML: tidsstämplade `<wpt>` + `<trk>` utan tider; fart och kurs finns bara som escapad HTML-text i `<desc>`/`<cmt>` — `trim_gpx.py` läser dem därifrån
- FR24-tider är hela sekunder (verklig kadens ca 2,2 s). OVRLEY räknar för GPX fram farten parvis (sträcka/tidsdifferens, `derive_numeric_rate_series`) utan utjämning — för GPX jämnas bara tempo och kurs ut — så farten hoppar t.ex. 62–166 kt där FR24:s uppmätta fart är 91–125 kt
- Lösning: skriv FR24:s uppmätta fart och kurs i varje punkt som Garmin TrackPointExtension v2 (`gpxtpx:speed` i m/s, `gpxtpx:course` i grader). OVRLEY:s `gpx-parser.js` läser extension-löv `speed` och `course`/`heading`, och direkt fart går före framräknad (`combine_series`). Verifierat genom att köra OVRLEY:s parser i Chromium 141 mot OVRLEY @ 13c3f41
- SRT-vägen (`gpx_to_dji_srt.py`) bär ingen fart, så där räknar OVRLEY fram den ur positionerna och den hoppar med FR24-data; vägen OVRLEY per klipp med GPX-import undviker det
- OVRLEY:s autosynk (`lib/video-sync.js`): offset = videons skapandetid − aktivitetens start; för ffprobe-/filnamnstider provas både `local` och `utc` och den som överlappar väljs. En GPX klippt exakt till klippet ger offset 0 s; misslyckas synken ("Video could not be synced with activity") sätts offset 0 manuellt
- FR24-höjden är barometrisk mot 1013 hPa (inte QNH), i 100-fotssteg från många småflygplanstranspondrar och 0 på marken — kan skilja mot GoPro-GPS:ens höjd i angränsande klipp med ca 30 ft per hPa
- FR24 MLAT kräver ≥3 mottagare och fungerar i Europa i regel först över ca 5 000–10 000 ft; för låg VFR krävs ADS-B. KML/CSV-export: Silver/Gold/Business (90 d / 1 år / 3 år historik) eller Contributor Plan för mottagarvärdar
- OVRLEY @ 13c3f41 (2026-10-10): CUDA-HEVC-vägen skalar fortfarande till `format=yuv420p`, så `_ovr`-filer blir 8-bit även från 10-bit-källor (blandas 10-bit-källa och `_ovr` i `xfade_concat.py` kraschar `hwdownload,format=nv12`)

## Statiska kartors defaultvärden

- `--margin`-default måste vara `-1` (av) för att undvika tyst efterbehandling; använd `--supersample` för skärpa via nedskalning, inte uppskalning

## Metadata-injektionsstrategier

- `inject360-inplace`-strategier: moov-last → trunkera och skriv om moov enbart; moov-first (OVRLEY faststart) → flytta moov till slutet och ersätt gamla moov med en `free`-box; säkerhetsspärr mot filer som fortfarande skrivs (mdat size = 0)

## Publiceringsformat

- GeoJSON vs KML: GitHub renderar `.geojson` nativt som interaktiva kartor; `.kml` är bäst för Google Earth Pro (höjd/3D)

## Verifierat kommando — KML/GeoJSON flygvisualisering

- `gpx_to_kml_dataurl.py --per-file --stakes 30 --geojson --no-url --out kml_files GS01*.gpx` ger bäst visuellt resultat i Google Earth Pro
- `--stakes` är ett intervall (var N:te GPS-punkt), inte ett antal — lägre värde ger fler stakes
- Använd inte `--extrude` tillsammans med stakes: vertexsömmarna skapar en tät stängseleffekt som helt skymmer stakes

## Marknadsundersökning — smart concat-verktyg (2026-09-19)

Ingen befintlig CLI eller verktyg täcker kombinationen: keyframe-medveten stream-copy av klippkroppar + omkodning endast i xfade-övergångsfönster + per-klipp hastighet med `audio=keep`-loop + automatisk YouTube-kapitelfil.

Sökta och avfärdade:
- **ffmpeg-concat** (transitive-bullshit) — kodar om hela videon via OpenGL-rendering, ingen stream copy, ingen hastighetsändring, ingen GoPro-hantering
- **royshil xfade-gist** — ren `filter_complex`, kodar om allt, ingen `-c copy`
- **fra00/autoclip** — GoPro-riktad AI-klippare (OpenCV-scoring, musik, crossfade) men ingen hastighetsrampning eller kapitelgenerering
- **benchan0527/gopro-dashcam-tool** — slår ihop GoPro-filer + GPS/hastighet som SRT, men ingen crossfade/hastighetsredigering
- Trek View- och Jeff Geerling-guiderna täcker bara grundläggande concat-demuxer + `-c copy` av GoPro-kapitelfiler

**Slutsats:** det egna skriptet är sannolikt unikt för denna kombination — ingen anledning att leta efter en färdig ersättning.
