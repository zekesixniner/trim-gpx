# trim-gpx

Klipper ett GPX-, KML- eller CSV-spår till exakt ett videoklipp. Gjort för den
dagen GoPro-kameran spelar in ett klipp **utan GPS-fix**: flygplanets spår från
[Flightradar24](https://www.flightradar24.com) ersätter kamerans GPS, och
resultatet går in i [OVRLEY](https://www.ovrley.cc) som vilken annan klipptelemetri
som helst.

🇬🇧 [English version of this README](README.md) ·
📖 [Manual: bygg upp ett klipps GPS från Flightradar24](MANUAL.sv.md) / [Manual in English](MANUAL.md)

```bash
trim_gpx.py fl03_4229ad6f.kml fl03_4229ad6f_GS010132.gpx --video /mnt/e/DCIM/100GOPRO/GS010132.360 --lang sv
```

```
Källa:    1526 tidsstämplade punkter, 2026-10-17 11:36:47Z – 12:35:00Z
Video:    GS010132.360: creation_time 2026-10-17T12:05:07Z, längd 62.208 s
Fönster:  2026-10-17 12:05:07Z – 12:06:09Z (62.208 s)
I fönstret: 29 källpunkter, största glapp mellan punkter 3 s
Höjd:     213–274 m (700–900 ft)
Markfart: 91–125 kt (uppmätt i källan, skrivs med)
Kurs:     060° → 189°

✅ Sparade 30 punkter → fl03_4229ad6f_GS010132.gpx
```

## Vad det gör

- **Läser Flightradar24:s exporter som de är**, KML eller CSV, och dessutom
  vilken GPX 1.0/1.1 eller KML med tidsstämplar som helst. gpsbabels
  konvertering av en Flightradar24-KML fungerar också.
- **Klipper exakt.** Första och sista punkten interpoleras, så spåret börjar på
  klippets första ögonblick och slutar på dess sista, på millisekunden.
- **Tar fönstret från klippet.** `--video` läser klippets `creation_time` och
  längd med ffprobe, även för kapitel 2, 3 … av en lång GoPro-inspelning.
- **Behåller den uppmätta farten och kursen.** Flightradar24:s tidsstämplar är
  hela sekunder medan punkterna kommer med två–tre sekunders mellanrum, så en
  fart som räknas fram ur positionerna hoppar fram och tillbaka: 62–166 kt i
  exemplet ovan, där flygplanet flög i 91–125 kt. trim-gpx skriver
  Flightradar24:s uppmätta markfart och kurs i varje punkt, och OVRLEY använder
  den farten i stället för att räkna fram en egen.
- **Fångar en fel tidszon.** Om fönstret missar spåret säger det vilken `--tz`
  som lägger fönstret inuti.
- **Skriver ut en sammanfattning** (punkter, största glapp, höjd, fart, kurs)
  att jämföra med videon.
- Bara Pythons standardbibliotek.

## Krav

- Python 3.9 eller senare
- ffprobe, som ingår i ffmpeg, för `--video` (`sudo apt install ffmpeg` i WSL/Ubuntu)
- Ett spår av flygningen. Från Flightradar24 kräver det ett konto som kan
  exportera KML/CSV och ett flygplan som sänder ADS-B — se
  [det här behöver du](MANUAL.sv.md#det-här-behöver-du) i manualen.

## Installation

Utvecklas och körs i WSL. Ingen virtuell miljö behövs.

```bash
git clone https://github.com/zekesixniner/trim-gpx.git ~/dev/trim-gpx
ln -s ~/dev/trim-gpx/trim_gpx.py ~/bin/trim_gpx.py      # ~/bin ligger i PATH
trim_gpx.py --help
```

Det är vanlig Python, så det bör fungera i Windows också, med Python och
ffprobe installerade (ffprobe följer med gyan.dev-bygget av ffmpeg). Det är
inte testat där ännu. Kopiera över skriptet från WSL, och gör det igen efter
varje uppdatering:

```bash
cp ~/dev/trim-gpx/trim_gpx.py /mnt/c/Users/<du>/bin/
```

```powershell
python $HOME\bin\trim_gpx.py --help
```

## Användning

```
trim_gpx.py INDATA UTDATA --video KLIPP                  [--tz H] [--hz N] [--lang sv]
trim_gpx.py INDATA UTDATA --start TID --duration LÄNGD   [--tz H] [--hz N] [--lang sv]
```

| flagga | |
|---|---|
| `INDATA` | spåret: Flightradar24-KML eller CSV, eller vilken GPX/KML med tider som helst |
| `UTDATA` | GPX 1.1-filen som ska skrivas |
| `--video KLIPP` | ta start och längd från klippet: dess `creation_time` och längd, lästa med ffprobe. Använd kamerans originalfil, t.ex. `GS010132.360` |
| `--start TID` | klippets start: `12:05:07` (datumet tas från spåret), `2026-10-17T12:05:07Z`, ffprobes `2026-10-17T12:05:07.000000Z` eller exiftools `2026:10:17 12:05:07`. En tid utan tidszon är UTC. Går före `--video` |
| `--duration LÄNGD` | klippets längd: `62.208` (sekunder) eller `1:02`. Går före `--video` |
| `--tz H` | starttiden är kamerans lokala klocka, UTC+H: `2` för svensk sommartid, `1` för vintertid. Standard `0`, kameran går på UTC |
| `--hz N` | sampla om till N punkter per sekund. OVRLEY behöver det inte |
| `--ffprobe SÖKVÄG` | vilken ffprobe som ska användas (standard: `ffprobe` i PATH) |
| `--lang en\|sv` | språk för utskrifterna (standard: `$GOPRO_LANG`, annars engelska) |
| `--version` | skriv ut versionen |

Slutstatus: `0` klart (även när spåret bara täcker en del av klippet, med en
varning), `1` fel, `2` fönstret ligger helt utanför spåret.

### Indataformat

| källa | vad som läses |
|---|---|
| Flightradar24-KML | Trail-placemarks: tid, position och höjd; fart och kurs ur varje punkts beskrivning |
| Flightradar24-CSV | `Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction`, höjd i fot och fart i knop |
| gpsbabels GPX av en Flightradar24-KML | de tidsstämplade `<wpt>`; fart och kurs ur beskrivningen som gpsbabel behåller i `<desc>` |
| vilken GPX 1.0/1.1 som helst | tidsstämplade `<trkpt>`, `<wpt>` och `<rtept>`; `<speed>` och `<course>` om de finns |
| annan KML | `Placemark` med `TimeStamp`, och `gx:Track` |

Punkter utan tid hoppas över; Flightradar24:s Route-linje har inga.

### Utdata

Ett GPX 1.1-spår med ett segment. Varje punkt har `<ele>` och `<time>`, med
millisekunder där det behövs. När källan hade dem bär varje punkt också den
uppmätta farten i m/s och kursen i grader, som Garmin TrackPointExtension:

```xml
<trkpt lat="56.1582910" lon="13.2884790"><ele>213.4</ele><time>2026-10-17T12:05:07Z</time><extensions><gpxtpx:TrackPointExtension><gpxtpx:speed>47.33</gpxtpx:speed><gpxtpx:course>60.0</gpxtpx:course></gpxtpx:TrackPointExtension></extensions></trkpt>
```

## Språk

Utskrifterna är på engelska eller svenska: `--lang sv`, eller sätt
`GOPRO_LANG=sv` en gång för alla verktygen (`export GOPRO_LANG=sv` i bash,
`$env:GOPRO_LANG = "sv"` i PowerShell), precis som i gopro-max-gpx-pipeline och
360-cli-tools.

## Tester

```bash
cd ~/dev/trim-gpx
python3 -m unittest discover -s tests -v
```

Testerna kör en syntetisk flygning som är uppbyggd som en Flightradar24-export,
med en attrapp i stället för ffprobe, så de behöver varken nätverk eller ffmpeg.
De täcker det exakta fönstret, uppmätt fart och kurs, en kurs som interpoleras
genom norr, omsampling, tidszoner och `--tz`-tipset, ett fönster som delvis
ligger utanför spåret, GoPro-kapitel, felmeddelandena och båda språken. KML,
CSV och gpsbabels GPX av samma flygning måste ge byte-identiska utdata.

Kontrollerat på riktiga data också. En flygning som exporterats från
Flightradar24 både som KML och CSV (1 526 punkter) gav byte-identisk GPX från
båda filerna i 60 slumpade fönster, och gpsbabels GPX av KML-filen gav samma fil
igen. OVRLEY:s egen GPX-parser (`app/src/lib/activity/gpx-parser.js`, OVRLEY
commit `13c3f41`), körd i Chromium, läste farten och kursen ur varje punkt.

## Relaterat

- [360-cli-tools](https://github.com/zekesixniner/360-cli-tools): `xfade_concat.py` och `titles_in_360.py`, som fogar ihop `_ovr`-klippen till filmen
- [gopro-max-gpx-pipeline](https://github.com/zekesixniner/gopro-max-gpx-pipeline): en sammanslagen video med telemetrin som SRT
- [gopro-telemetry-tool](https://github.com/zekesixniner/gopro-telemetry-tool): kamerans egen GPX ur `.360`-filen
- [inject360-inplace](https://github.com/zekesixniner/inject360-inplace): sfärisk metadata, alltid sista steget

## Licens

MIT, se [LICENSE](LICENSE).
