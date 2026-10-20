# trim-gpx

Ser till att varje GoPro-klipp har GPS-telemetri för hela sin längd. Det
kontrollerar GPX-filen som extraherats ur varje klipp mot klippet självt, och
fyller det som saknas från ett annat spår — i första hand en
[SkyDemon](https://www.skydemon.aero)-logg, i andra hand ett
[Flightradar24](https://www.flightradar24.com)-spår — medan kamerans egna
punkter ligger kvar där den har dem. Resultatet går in i
[OVRLEY](https://www.ovrley.cc) som vilken annan klipptelemetri som helst.

Det kan också klippa vilket spår som helst till exakt ett klipp.

🇬🇧 [English version of this README](README.md) ·
📖 [Manual: komplettera ett klipps GPS](MANUAL.sv.md) / [Manual in English](MANUAL.md)

```bash
cd /sökväg/till/flygningen      # klippens GPX-filer, plus SkyDemon/Flightradar24-spår
trim_gpx.py --check . --video-dir /mnt/e/DCIM/100GOPRO --lang sv
```

```
Kontrollerar 1 klipp, videor i /mnt/e/DCIM/100GOPRO:
  GS010130.gpx  saknas     63.1 s av 203.093 s: 10:00:27Z – 10:01:30Z · kamerans klocka +0.03 s

GS010130.gpx: saknar 10:00:27Z – 10:01:30Z (63.1 s av 203.093 s)
  Fyll från:
    1  fl02_42294bf5.gpx  Flightradar24  täcker 63.1 s av 63.1 s
  Välj 1–1 (Enter = 1), en annan fil, eller n för att lämna luckan:
  ✓ 63.1 s från fl02_42294bf5.gpx (30 punkter); matchat mot kameran: höjd +182 ft, position 3 m
  ✅ GS010130.gpx uppdaterad: 1401 kamerapunkter + 30 ifyllda (originalet: GS010130.gpx.orig)

Alla klipp har data för hela sin längd (kontrollerade: 1).
```

## Vad det gör

**Kontroll av ett klipps egen GPX** (`--check`)

- **Hittar det som saknas.** Varje GPX jämförs med klippets `creation_time` och
  längd (ur `.360`-filen, lästa med ffprobe): ett klipp helt utan fix, ett som
  väntade på fix, eller ett med ett avbrott på mer än 2 sekunder.
- **Ser igenom gopro-telemetrys platshållare.** gopro-telemetry börjar sin GPX
  med en kopia av den första fixen, daterad till första bildrutan. Efter en lång
  väntan på fix ligger den punkten långt från där kameran var, och OVRLEY står
  still på den tills de riktiga data börjar. Den tas bort.
- **Kontrollerar kamerans klocka.** Platshållaren bär GPS-tiden för första
  bildrutan, så kamerans klocka kan jämföras med GPS-tiden för varje klipp som
  har fix.
- **Erbjuder det som kan fylla luckan.** Det letar bredvid klippen efter spår
  som täcker tiden som saknas, erbjuder en SkyDemon-logg före ett
  Flightradar24-spår, och frågar innan det används ett. `--fill` anger ett spår
  själv, och `--yes` tar det bästa utan att fråga.
- **Passar ihop fyllnaden med kameran.** Vid varje skarv flyttas den ifyllda
  sträckan så att den möter kamerans position och GPS-höjd: Flightradar24:s
  barometriska höjd låg 182 ft under kamerans GPS-höjd i exemplet ovan. Ett
  klipp utan egen fix får höjdskillnaden från grannklippen.
- **Uppdaterar klippets GPX på plats** och sparar originalet som `.gpx.orig`,
  så att OVRLEY och gopro-max-gpx-pipeline hittar den under det vanliga namnet.
  Ifyllda punkter anger sin källa i `<src>`.
- **Tar en hel mapp på en gång**: en rad per klipp, frågor bara för de klipp
  som har luckor. Klipp som fyllts i tidigare räknas som kompletta.

**Klippning av ett spår till ett klipp**

- **Läser Flightradar24:s exporter som de är**, KML eller CSV, och dessutom
  vilken GPX 1.0/1.1 eller KML med tidsstämplar som helst, och gpsbabels
  konvertering av en Flightradar24-KML.
- **Klipper exakt**: första och sista punkten interpoleras till klippets första
  och sista ögonblick, på millisekunden. `--video` tar fönstret från klippet,
  även för kapitel 2, 3 … av en lång inspelning.
- **Fångar en fel tidszon**: om fönstret missar spåret säger det vilken `--tz`
  som lägger fönstret inuti.

**Båda** behåller den uppmätta farten och kursen från Flightradar24 och
SkyDemon. Flightradar24:s tidsstämplar är hela sekunder medan punkterna kommer
med två–tre sekunders mellanrum, så en fart som räknas fram ur positionerna
hoppar fram och tillbaka (62–166 kt där flygplanet flög i 91–125 kt). De
uppmätta värdena skrivs i varje punkt som Garmin TrackPointExtension, och
OVRLEY använder den farten i stället för att räkna fram en egen. Bara Pythons
standardbibliotek.

**Båda** sparar också varje Flightradar24-KML eller CSV de läser som GPX
bredvid, med samma namn (`4229ad6f.csv` → `4229ad6f.gpx`), för program som vill
ha GPX. gpsbabel gör det, från CSV-filen när båda finns, eftersom farten och
kursen då följer med som GPX 1.0:s `<speed>` och `<course>`. En GPX som redan
finns byts bara ut om gpsbabel gjorde den och exporten är nyare, och
`--dry-run` skriver ingen. Den GPX-filen är inte till OVRLEY, som bara tar
farten ur extensions: ge OVRLEY den ifyllda kamera-GPX:en eller ett klippt spår.

## Krav

- Python 3.9 eller senare
- ffprobe, som ingår i ffmpeg (`sudo apt install ffmpeg` i WSL/Ubuntu)
- gpsbabel, för att spara Flightradar24:s exporter som GPX (`sudo apt install
  gpsbabel`); utan det blir det en varning och allt annat fungerar
- För ifyllnad: en SkyDemon-logg av flygningen, eller en Flightradar24-export,
  vilket kräver ett konto som kan exportera KML/CSV och ett flygplan som sänder
  ADS-B — se [det här behöver du](MANUAL.sv.md#det-här-behöver-du) i manualen

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
trim_gpx.py --check [KAMERA.gpx | MAPP ...]  [--video-dir MAPP] [--fill SPÅR] [--yes] [--dry-run]
trim_gpx.py SPÅR UTDATA --video KLIPP                  [--tz H] [--hz N]
trim_gpx.py SPÅR UTDATA --start TID --duration LÄNGD   [--tz H] [--hz N]
```

### Kontroll av kamerans GPX

| flagga | |
|---|---|
| `--check` | kontrollera varje kamera-GPX (`GS010130.gpx` …) mot sitt klipp och fyll det som saknas |
| `KAMERA.gpx`, `MAPP` | GPX-filerna som ska kontrolleras, eller mappar med dem (standard: den här mappen) |
| `--video-dir MAPP` | var klippens `.360`-filer ligger (standard: bredvid GPX-filen). En `.mp4` används om det inte finns någon `.360`, med en varning |
| `--video KLIPP` | klippets fil, för en enda GPX |
| `--fill SPÅR` | fyll från det här spåret först, utan att fråga (kan upprepas, i önskad ordning) |
| `--search MAPP` | leta efter spår i den här mappen också (kan upprepas) |
| `-y`, `--yes` | fyll från det bästa spåret som hittas, utan att fråga |
| `--ask`, `--no-ask` | fråga innan ifyllnad, eller aldrig (standard: fråga när det körs i en terminal) |
| `--dry-run` | bara rapportera, ändra ingenting |
| `--refill` | gör om sträckor som fyllts i vid en tidigare körning; kamerans punkter behålls |
| `-o GPX`, `--output GPX` | skriv hit i stället för att uppdatera kamerans GPX (ett klipp) |
| `--max-gap S` | ett hål i kamerans GPS som är längre än så räknas som saknat (standard `2` s) |
| `--tz H` | klippens `creation_time` är lokal tid, UTC+H. Ett klipp vars gopro-telemetry-GPX har fix tidsbestäms av GPS och behöver ingen `--tz` |

Spår som erbjuds för ifyllnad, i den här ordningen: SkyDemon-loggar, andra
GPS-spår, Flightradar24-exporter. Filer från kameran (`GS…`), filer som det här
skriptet har skrivit, gpsbabels GPX av en Flightradar24-export som ligger
bredvid den, och samma flygning exporterad flera gånger utelämnas.

Slutstatus: `0` alla klipp kompletta, `1` ett klipp kunde inte kontrolleras
(t.ex. ingen video), `3` ett klipp saknar fortfarande data.

### Klippning av ett spår

| flagga | |
|---|---|
| `SPÅR` | spåret: Flightradar24-KML eller CSV, eller vilken GPX/KML med tider som helst |
| `UTDATA` | GPX 1.1-filen som ska skrivas |
| `--video KLIPP` | ta start och längd från klippet: dess `creation_time` och längd, lästa med ffprobe. Använd kamerans originalfil, t.ex. `GS010132.360` |
| `--start TID` | klippets start: `12:05:07` (datumet tas från spåret), `2026-10-17T12:05:07Z`, ffprobes `2026-10-17T12:05:07.000000Z` eller exiftools `2026:10:17 12:05:07`. En tid utan tidszon är UTC. Går före `--video` |
| `--duration LÄNGD` | klippets längd: `62.208` (sekunder) eller `1:02`. Går före `--video` |
| `--tz H` | starttiden är kamerans lokala klocka, UTC+H: `2` för svensk sommartid, `1` för vintertid. Standard `0`, kameran går på UTC |
| `--hz N` | sampla om till N punkter per sekund. OVRLEY behöver det inte |

Slutstatus: `0` klart (även när spåret bara täcker en del av klippet, med en
varning), `1` fel, `2` fönstret ligger helt utanför spåret.

### Gemensamma flaggor

| flagga | |
|---|---|
| `--ffprobe SÖKVÄG` | vilken ffprobe som ska användas (standard: `ffprobe` i PATH) |
| `--gpsbabel SÖKVÄG` | vilken gpsbabel som sparar Flightradar24:s KML/CSV som GPX (standard: `gpsbabel` i PATH) |
| `--lang en\|sv` | språk för utskrifterna (standard: `$GOPRO_LANG`, annars engelska) |
| `--version` | skriv ut versionen |

### Indataformat

| källa | vad som läses |
|---|---|
| kamerans GPX (gopro-telemetry, gpmf2gpx.py) | tidsstämplade `<trkpt>`; punkter med `<fix>none</fix>` eller fix 0 hoppas över |
| SkyDemons GPX | `<trkpt>` med `<ele>`, `<speed>` (m/s) och `<time>` |
| Flightradar24-KML | Trail-placemarks: tid, position och höjd; fart och kurs ur varje punkts beskrivning |
| Flightradar24-CSV | `Timestamp,UTC,Callsign,Position,Altitude,Speed,Direction`, höjd i fot och fart i knop |
| gpsbabels GPX av en Flightradar24-KML | de tidsstämplade `<wpt>`; fart och kurs ur beskrivningen som gpsbabel behåller i `<desc>` |
| vilken GPX 1.0/1.1 som helst | tidsstämplade `<trkpt>`, `<wpt>` och `<rtept>`; `<speed>` och `<course>` om de finns |
| annan KML | `Placemark` med `TimeStamp`, och `gx:Track` |

Punkter utan tid hoppas över; Flightradar24:s Route-linje har inga.

### Utdata

Ett GPX 1.1-spår med ett segment, från klippets första ögonblick till dess
sista. Varje punkt har `<ele>` och `<time>`, med millisekunder där det behövs.
En punkt som fyllts i av `--check` anger sin källa i `<src>`, och när källan
hade dem bär punkten den uppmätta farten i m/s och kursen i grader, som Garmin
TrackPointExtension:

```xml
<trkpt lat="56.0352876" lon="13.2601768"><ele>329.9</ele><time>2026-10-17T10:00:27Z</time><src>fl02_42294bf5.gpx</src><extensions><gpxtpx:TrackPointExtension><gpxtpx:speed>50.42</gpxtpx:speed><gpxtpx:course>356.0</gpxtpx:course></gpxtpx:TrackPointExtension></extensions></trkpt>
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

Testerna behöver varken nätverk eller ffmpeg: en syntetisk flygning, uppbyggd
som en Flightradar24-export, "flygs" av en kamera som skriver GPX i
gopro-telemetry-stil med 10 Hz och av en SkyDemon-liknande logger, och
attrapper ersätter ffprobe och gpsbabel.

- `tests/test_check.py` täcker `--check`: ett komplett klipp som lämnas orört,
  luckor i början, i mitten och i slutet, ett klipp utan fix som tar sin höjd
  från grannarna, SkyDemon som erbjuds före Flightradar24, platshållaren, en
  kameraklocka på lokal tid, svar som skrivs vid frågan, en hel mapp, en
  omkörning och `--refill`, och en video som saknas. Dessutom att
  Flightradar24-exporterna sparas som GPX: en gång, från CSV-filen, igen när
  exporten är nyare, aldrig över en GPX som gpsbabel inte gjort, inte med
  `--dry-run`, och bara en varning när gpsbabel saknas eller misslyckas. Finns
  gpsbabel installerat kör ett test det riktiga på en KML och en CSV och
  kontrollerar att varje punkt behåller tid, position, höjd, fart och kurs.
- `tests/test_trim_gpx.py` täcker klippning: det exakta fönstret, uppmätt fart
  och kurs, en kurs genom norr, omsampling, tidszoner, GoPro-kapitel,
  felmeddelanden och båda språken. KML, CSV och gpsbabels GPX av samma flygning
  måste ge byte-identiska utdata, och spåret sparas som GPX men aldrig över
  UTDATA.

Kontrollerat på riktiga data också. På ett riktigt klipp där kameran väntade
63 s på fix fyllde `--check` luckan från en Flightradar24-export med höjd och
position ihoppassade i skarven (inget höjdsteg, inget ryck i farten). En
flygning som exporterats från Flightradar24 både som KML och CSV gav
byte-identisk GPX från båda filerna, och gpsbabels GPX av KML-filen gav samma
fil igen. En SkyDemon-logg lästes med sin fart. OVRLEY:s egen GPX-parser
(`app/src/lib/activity/gpx-parser.js`, OVRLEY commit `13c3f41`), körd i
Chromium, läste den uppmätta farten och kursen ur varje ifylld punkt.

## Relaterat

- [360-cli-tools](https://github.com/zekesixniner/360-cli-tools): `xfade_concat.py` och `titles_in_360.py`, som fogar ihop `_ovr`-klippen till filmen
- [gopro-max-gpx-pipeline](https://github.com/zekesixniner/gopro-max-gpx-pipeline): en sammanslagen video med telemetrin som SRT
- [gopro-telemetry-tool](https://github.com/zekesixniner/gopro-telemetry-tool): kamerans egen GPX ur `.360`-filen
- [inject360-inplace](https://github.com/zekesixniner/inject360-inplace): sfärisk metadata, alltid sista steget

## Licens

MIT, se [LICENSE](LICENSE).
