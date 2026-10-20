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
- gopro-telemetry (GPX-preset): tider är GPS-tid (GPS9 days/secs); första punkten är en platshållare = kopia av första fixen daterad till första bildrutan (`date − cts`). Efter lång väntan på fix ligger den långt från verklig position och OVRLEY står still (GS010130: 63 s). Dess tid mot `creation_time` ger kameraklockans fel (GS010130: +0,026 s; `creation_time` har hela sekunder)
- extract.js kör `GPSFix: 3, GPSPrecision: 500, WrongSpeed: 120, smooth: 3` → `<fix>`-värden blir utjämnade flyttal (1,5 … 3) och kamerans första punkter efter fix släpar lite

## Telemetrisynk och GPX-giltighet

- DJI Format B SRT löser OVRLEY-telemetrisynkproblemet: elapsed timecode för framesynk plus riktig wall-clock-tid i `HOME(...)`-raden, vilket undviker problemet att en naivt sammanslagen GPX behåller verkliga pauser
- `<fix>`-sanering: `gopro-telemetry`s smooth-option ger flyttalsvärden i `<fix>`-element som misslyckas mot `gpxpy`s strikta schemavalidering; kräver en `re.sub`-sanerare

## Komplettera klipp utan GPS: trim-gpx (2026-10-19/20)

- Repot `trim-gpx` (`~/dev/trim-gpx`, `trim_gpx.py` 1.2.1, manual `MANUAL.md`/`MANUAL.sv.md`). Huvudflöde: `trim_gpx.py --check . --video-dir /mnt/e/…/100GOPRO` — kontrollerar varje kamera-GPX mot klippets `creation_time`/längd, fyller luckor (> 2 s) från SkyDemon i första hand och FR24 i andra hand, behåller kamerans punkter, uppdaterar GPX på plats (original `.gpx.orig`, ifyllda punkter märkta `<src>`), höjd/position matchas vid skarvar (10 s kameradata; klipp utan fix tar höjden från grannklipp ≤ 30 min). Klippläget: `trim_gpx.py <fr24>.kml|.csv ut.gpx --video GS010132.360`
- OVRLEY visar GPX-filens längd från första till sista punkt: en GPX som börjar senare än videon syns kortare (1.2.0 när början inte gick att fylla, GS010131: 05:47 mot videons 06:26). Från 1.2.1 täcker GPX-filen alltid klippet: en punkt på första/sista bildrutan står kvar på närmaste position (`<src>hold</src>`, utan fart och kurs) och räknas inte som data; en omkörning lägger till den i 1.2.0-filer. gopro-telemetrys platshållare fyllde samma funktion i originalet
- Kamera mot FR24 (GS010130 + fl02): kamerans GPS-höjd +182…197 ft över FR24:s barometriska, position ~3–10 m, tid ~0,1 s. Matchning av höjd mot exakta skarvskillnaden (utfasning över 10 s) men position mot medelavvikelsen — exakt positionsmatchning mot kamerans släpande första punkt gav fartdipp
- SkyDemon-GPX (creator "SkyDemon Plan v4.3.3.0"): `<trkpt>` med `<ele>` (GPS), `<speed>` (m/s, icke-standard i GPX 1.1), `<time>` hela sekunder, ~5 s kadens, dubblerade tider, ingen kurs
- Kamerans klocka: MAX2:an skriver UTC (GS010130 och GS010132 mot GPS/FR24); `--tz 2` lade GS010132 1,5 h före start. Klippläget föreslår själv den `--tz` (0/1/2) som träffar spåret
- FR24:s CSV-export (verifierad på riktig export): `Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction` — epoch, ISO-UTC, `"lat,lon"` i citattecken, höjd i fot, fart i knop, kurs i grader. KML och CSV av samma flygning ger identiska punkter och byte-identisk GPX
- gpsbabel 1.9.0 av en FR24-KML: tidsstämplade `<wpt>` + `<trk>` utan tider; fart och kurs finns bara som escapad HTML-text i `<desc>`/`<cmt>` — `trim_gpx.py` läser dem därifrån
- gpsbabel som konverterare (trim_gpx 1.2.0 sparar varje FR24-export den läser som `<namn>.gpx` bredvid, från CSV:n om båda finns): KML → `gpsbabel -i kml -f X.kml -x nuketypes,tracks,routes -x transform,trk=wpt,del -o gpx -F X.gpx` ger ett tidsstämplat spår (utan filtren: `<wpt>` + ett otidsatt `<trk>`). unicsv klarar inte FR24:s CSV (epoch-tid, `"lat,lon"` i ett fält); en xcsv-stil (`FR24_CSV_STYLE` i skriptet) gör det: `LAT_/LON_HUMAN_READABLE` hoppar över citattecknen, PROLOGUE hoppar över rubrikraden efter antal rader, `TIMET_TIME`, `ALT_FEET`, `PATH_SPEED_KNOTS`, `PATH_COURSE`. GPX 1.0-utdata behåller `<speed>`/`<course>`, `gpxver=1.1` tappar dem. OVRLEY läser fart bara ur `<extensions>`, så gpsbabel-GPX:en är inte för OVRLEY
- FR24-tider är hela sekunder (verklig kadens ca 2,2 s). OVRLEY räknar för GPX fram farten parvis (sträcka/tidsdifferens, `derive_numeric_rate_series`) utan utjämning — för GPX jämnas bara tempo och kurs ut — så farten hoppar t.ex. 62–166 kt där FR24:s uppmätta fart är 91–125 kt
- Lösning: skriv uppmätt fart och kurs i varje punkt som Garmin TrackPointExtension v2 (`gpxtpx:speed` i m/s, `gpxtpx:course` i grader). OVRLEY:s `gpx-parser.js` läser extension-löv `speed` och `course`/`heading`, och direkt fart går före framräknad (`combine_series`). Verifierat genom att köra OVRLEY:s parser i Chromium 141 mot OVRLEY @ 13c3f41
- SRT-vägen (`gpx_to_dji_srt.py`) bär ingen fart, så där räknar OVRLEY fram den ur positionerna och den hoppar med FR24-data; vägen OVRLEY per klipp med GPX-import undviker det
- OVRLEY:s autosynk (`lib/video-sync.js`): offset = videons skapandetid − aktivitetens start; för ffprobe-/filnamnstider provas både `local` och `utc` och den som överlappar väljs. En GPX som börjar på klippets första bildruta ger offset 0 s; misslyckas synken ("Video could not be synced with activity") sätts offset 0 manuellt
- FR24-höjden är barometrisk mot 1013 hPa (inte QNH), i 100-fotssteg från många småflygplanstranspondrar. FR24:s 0 ft betyder ”lågt”, inte ”på marken”: i fl02 och fl03 går höjden direkt mellan 200 och 0 (100 förekommer aldrig), och vid fl02:s landning (GS010130) gick FR24 till 0 när kamerans GPS var ~196 ft över banan, 20 s före sättningen. Fyllning över 0-ft-punkter ger en konstant höjd = 0 + skarvförskjutningen (GS010131: 238 ft MSL ≈ 106 ft över banan): rimligt strax efter start/före landning, ~100 ft för högt på banan; ingen särbehandling än (2026-10-20). Kamerans GPS på marken i Ljungbyhed: 132 ft MSL; kamera minus FR24 ≈ +225 ft den dagen (motsvarar QNH ~1021 hPa)
- FR24 på marken i Ljungbyhed (ESTL) är glest: fl02 har två punkter i 0 kt på 5,5 min (transpondern var på) och ingen under minuten fram till rullningen; i båda flygningarna börjar sammanhängande spår först vid ~75 kt, runt lättningen. GS010131 (fl03) enligt filmen: stillastående på tröskeln 11R till 11:36:14Z, rullning från 11:36:14Z; FR24:s första punkt 11:36:47Z i 77 kt. På marken når ADS-B bara mottagare inom ett par mil med fri sikt
- MAX2:ans GPS9 enligt `exiftool -ee` (GS010131): 10 prov/s hela klippet, `GPS Altitude System: MSLV` (höjden är MSL). Utan fix (Measure Mode 0) levererar mottagaren ändå positioner från ~20 s efter inspelningsstart (11:36:30Z på banan i 54 kt, 11:36:38Z 69 kt, från 11:36:48Z inom ~17 m från FR24), men DOP säger inget om kvaliteten (en burst med DOP 4,45 låg 110 m fel) och höjden är oanvändbar (0–115 ft, under banan). Första 3D-fix 11:37:00.7Z med DOP ~8,7, DOP ≤ 5 från 11:37:17Z; höjden stabiliseras ~20 s senare (kamera − FR24: +96 → +187 → ~+225 ft). extract.js (`GPSFix: 3`, `GPSPrecision: 500`) slänger allt före 11:37:17Z. Kontroll: `exiftool -ee -n -q -q -p '$GPSDateTime $GPSMeasureMode $GPSDOP $GPSLatitude $GPSLongitude $GPSAltitude $GPSSpeed' X.360` (GPSSpeed i km/h)
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
