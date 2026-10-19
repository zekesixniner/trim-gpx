# Manual: bygg upp ett klipps GPS-spår från Flightradar24

🇬🇧 [English](MANUAL.md) · [Tillbaka till README](README.sv.md)

Ibland spelar GoPro MAX2 in ett klipp utan GPS-fix. Den slogs på strax innan,
eller satt för långt in i cockpit för att se himlen. Telemetrin ur den
`.360`-filen har då inga positioner, och OVRLEY har ingenting att rita för
klippet: ingen karta, ingen fart, ingen höjd.

Om Flightradar24 spårade flygningen kan deras spår ersätta kamerans GPS. Den
här manualen går från den tomma GPX-filen till klippet i den färdiga filmen.

- [Det här behöver du](#det-här-behöver-du)
- [Flödet](#flödet)
- [1. Kontrollera att klippet saknar GPS](#1-kontrollera-att-klippet-saknar-gps)
- [2. Ladda ner flygningen från Flightradar24](#2-ladda-ner-flygningen-från-flightradar24)
- [3. Klipp spåret till klippet](#3-klipp-spåret-till-klippet)
- [4. Jämför resultatet med videon](#4-jämför-resultatet-med-videon)
- [5. Om fönstret missar spåret: kamerans klocka](#5-om-fönstret-missar-spåret-kamerans-klocka)
- [6. OVRLEY](#6-ovrley)
- [7. Tillbaka in i filmen](#7-tillbaka-in-i-filmen)
- [Vad ett Flightradar24-spår kan och inte kan berätta](#vad-ett-flightradar24-spår-kan-och-inte-kan-berätta)
- [Felsökning](#felsökning)
- [Ett exempel: GS010132, 17 oktober 2026](#ett-exempel-gs010132-17-oktober-2026)

## Det här behöver du

**Flightradar24 måste ha spårat flygningen med positioner.**

- Flygplanets transponder måste vara på och sända **ADS-B**: Mode S extended
  squitter med en GNSS-källa för positionen. Det är därifrån Flightradar24 får
  positioner, fart och kurs.
- Utan ADS-B kan Flightradar24 bara positionera ett flygplan med MLAT, genom
  att tidsmäta transponderns svar vid tre eller fler mottagare. I större delen
  av Europa fungerar det över ungefär 5 000–10 000 ft
  ([Flightradar24](https://www.flightradar24.com/how-it-works/mlat)). För en
  VFR-flygning på några tusen fot betyder ingen ADS-B alltså inget spår.
- En mottagare måste höra flygplanet. Lågt och på marken har täckningen hål.
  trim-gpx visar det största glappet så att du ser dem. En egen mottagare nära
  hemmafältet hjälper.

**Du måste kunna ladda ner flygningen.** Flightradar24:s KML- och CSV-export
finns för Silver, Gold och Business, med 90 dagars, ett års respektive tre års
historik
([Flightradar24](https://www.flightradar24.com/blog/inside-flightradar24/using-the-new-flightradar24-kml-and-csv-export-tools/)).
Den som har en Flightradar24-mottagare får den kostnadsfria Contributor Plan,
och det är med den som underhållaren laddar ner. Ladda ner flygningen medan den
fortfarande finns inom din plans historik.

**Kamerans klocka bör gå rätt** på några sekunder när. Vilken tidszon den
skriver kontrolleras i [steg 5](#5-om-fönstret-missar-spåret-kamerans-klocka).

**Verktyg:** `trim_gpx.py` ([installation](README.sv.md#installation)),
ffprobe (`sudo apt install ffmpeg` i WSL) och OVRLEY.

## Flödet

```
 kameran                           Flightradar24
 GS010132.360                      fl03_4229ad6f.kml (eller .csv)
   creation_time, längd              tid, position, höjd, fart, kurs
        │                                  │
        └────────────────┬─────────────────┘
                         ▼
        trim_gpx.py --video GS010132.360                    WSL
                         │
                         ▼
        fl03_4229ad6f_GS010132.gpx    exakt klippets 62,208 s
                         │
 GoPro Player            │
 GS010132.mp4 ──────────►┤
                         ▼
        OVRLEY (MP4 + GPX) ──► GS010132_ovr.mp4                 Windows
                         │
                         ▼
        xfade_concat.py → titles_in_360.py → inject360-inplace (sist)
```

## 1. Kontrollera att klippet saknar GPS

Extrahera telemetrin som vanligt (gopro-telemetry-tool eller gpmf2gpx.py). Ett
klipp som spelats in utan fix ger en GPX utan punkter:

```bash
grep -c '<trkpt' GS010132.gpx
0
```

Faller GPS:en bara bort under en del av klippet behåller du kamerans eget spår,
eftersom OVRLEY interpolerar över ett kort avbrott. Ta Flightradar24-spåret för
hela klippet när glappet är för långt för det.

## 2. Ladda ner flygningen från Flightradar24

1. Logga in på flightradar24.com och sök på flygplanets registrering.
2. Leta upp flygningen i listan över tidigare flygningar på flygplanets sida.
3. Tryck på **KML** (eller **CSV**) för den flygningen.

Döp filen efter din flygning och behåll Flightradar24:s flyg-ID, t.ex.
`fl03_4229ad6f.kml`: dagens tredje flygning, Flightradar24-flygning `4229ad6f`.

**KML eller CSV?** Spelar ingen roll. Båda har tid, position, höjd, markfart
och kurs för varje punkt, och trim-gpx gör samma GPX av dem. KML-filen kan
dessutom öppnas i Google Earth om du vill titta på flygningen.

Ingen konvertering behövs, eftersom trim-gpx läser exporten som den är. Har du
redan konverterat den med gpsbabel fungerar den filen också. gpsbabel behåller
Flightradar24:s fart och kurs som text i varje punkts `<desc>`, och trim-gpx
läser dem därifrån.

## 3. Klipp spåret till klippet

Peka `--video` på kamerans originalfil. trim-gpx läser dess `creation_time` och
längd med ffprobe:

```bash
cd /sökväg/till/flygningen
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

(`--lang sv` behövs inte om du har `GOPRO_LANG=sv` satt.)

Använd kamerans `.360`, från kortet eller din kopia av det. Dess
`creation_time` är kamerans egen uppgift om när inspelningen började.

Utan `--video` läser du själv ut samma två värden och anger dem som `--start`
och `--duration`:

```bash
ffprobe -v error -show_entries format=duration:format_tags=creation_time -of default=nw=1 GS010132.360
duration=62.208000
TAG:creation_time=2026-10-17T12:05:07.000000Z

trim_gpx.py fl03_4229ad6f.kml fl03_4229ad6f_GS010132.gpx --start 2026-10-17T12:05:07Z --duration 62.208
```

**Kapitel.** En lång inspelning delas upp i kapitel: `GS010068`, `GS020068`,
`GS030068` och så vidare. För kapitel 2 och framåt kontrollerar `--video` om
kapitlets `creation_time` är dess egen start eller hela inspelningens, genom att
jämföra med kapitel 1. Är det inspelningens start läggs de tidigare kapitlens
längd till, och utskriften säger det:

```
Video:    GS030068.360: creation_time 2026-10-17T12:00:00Z, längd 4 s
          kapitel 3 av inspelning 0068: dess creation_time är inspelningens start, lägger till 2 tidigare kapitel (18 s)
```

Det kräver att inspelningens alla kapitel ligger i samma mapp. Ett kapitel som
ligger ensamt ger i stället en varning. Utan `--video` gör du samma summering
för hand.

## 4. Jämför resultatet med videon

Sammanfattningen finns till för att jämföras med bilden.

- **Fönster.** Ingen `[VARNING]` och inget `[FEL]` betyder att hela klippet
  ligger inuti spåret.
- **Största glapp.** Flightradar24 levererar en punkt med några sekunders
  mellanrum, så ett glapp på några sekunder är normalt. Tiotals sekunder är ett
  hål i täckningen, och spåret går rakt över det.
- **Höjd, fart och kurs** i början och slutet av klippet. `Kurs: 060° → 189°`
  är en högersväng på ungefär 130°. Syns en sådan i videon? En stigning, en
  sväng in på final eller banriktningen vid start är lätta att kontrollera.
- GPX-filen kan också öppnas i Google Earth, GPXSee eller liknande, så att du
  ser att spåret ligger där du flög.

## 5. Om fönstret missar spåret: kamerans klocka

`creation_time` är kamerans klocka, och filen märker den alltid som UTC (`Z`),
vad klockan än var inställd på. Var den inställd på lokal tid hamnar fönstret
en eller två timmar fel, utanför flygningen, och trim-gpx säger då vilken
offset som passar:

```
Fönster:  2026-10-17 10:05:07Z – 10:06:09Z (62.208 s)
[FEL]     Fönstret ligger helt utanför spåret.
          Utan --tz hamnar fönstret 12:05:07Z – 12:06:09Z, helt inuti spåret.
```

Här hade `--tz 2` angetts, men kameran skriver UTC. `--tz 2` betyder
"starttiden är svensk sommartid" (UTC+2), `--tz 1` vintertid. Den MAX2 som det
här utvecklades med skriver UTC, kontrollerat mot Flightradar24, och behöver
alltså ingen `--tz`. Kontrollera din egen kamera en gång mot en flygning.

En fel tidszon upptäcks bara när den andra tiden hamnar utanför flygningen. På
en flygning som är så lång att den täcker båda tiderna jämför du
sammanfattningen med videon innan du litar på resultatet.

En klocka som går några sekunder fel syns som en overlay som ligger lite före
eller efter bilden. I 100 kt är en sekund ungefär 50 m. Justera det i OVRLEY
([steg 6](#6-ovrley)) eller flytta `--start`.

## 6. OVRLEY

1. Importera det stitchade klippet, GoPro Players MP4 (t.ex. `GS010132.mp4`),
   och GPX-filen som aktivitet.
2. **Synk.** OVRLEY:s automatiska synk jämför videons skapandetid med GPX-filen
   och provar den både som lokal tid och som UTC. Med en GPX som är klippt exakt
   till klippet landar den på en synkoffset på 0 s. Säger OVRLEY *Video could
   not be synced with activity*, till exempel för att MP4-filen har tappat sin
   skapandetid, sätter du synkoffseten till 0 för hand. GPX-filen börjar på
   klippets första bildruta.
3. **Finjustera** om en sväng i bilden och på kartan inte stämmer överens.
   Synkoffseten kan nudgas en sekund i taget.
4. Lägg upp widgetarna och rendera som för de andra klippen: `GS010132_ovr.mp4`.

Fartwidgeten visar Flightradar24:s uppmätta markfart. OVRLEY:s GPX-import läser
den ur varje punkt och använder den i stället för att räkna fram farten ur
positionerna (kontrollerat mot OVRLEY:s källkod, commit `13c3f41`).

OVRLEY:s NVIDIA-väg skriver 8-bitarsvideo, även från GoPro Players
10-bitsexport, så `GS010132_ovr.mp4` passar ihop med de andra `_ovr`-klippen.
Lägg inte själva 10-bitsexporten i samma körning av `xfade_concat.py`, för då
kraschar den vid första övergången med `Invalid output format nv12 for hwframe
download`.

## 7. Tillbaka in i filmen

Slå ihop som vanligt, med det nya klippet på sin plats:

```powershell
python $HOME\bin\xfade_concat.py -o GS00131-134_ovr.mp4 GS010131_ovr.mp4 GS010132_ovr.mp4 GS010133_ovr.mp4 GS010134_ovr.mp4
```

Sedan `titles_in_360.py`, och `inject360-inplace` sist.

### Med gopro-max-gpx-pipeline i stället

Gör du en sammanslagen video med telemetrin som SRT
([gopro-max-gpx-pipeline](https://github.com/zekesixniner/gopro-max-gpx-pipeline))
lägger du den klippta GPX-filen i stället för klippets tomma, under samma namn,
innan du kör `gpx_to_dji_srt.py`:

```bash
mv GS010132.gpx GS010132.gpx.empty
cp fl03_4229ad6f_GS010132.gpx GS010132.gpx
gpx_to_dji_srt.py telemetry.srt --pairs-from-basenames 'GS0*.gpx' --video-dir .
```

Position, höjd och klocka kommer då med för det klippet. SRT-filen har dock
ingen fart, så OVRLEY räknar fram den ur positionerna, och med Flightradar24:s
hela sekunder hoppar den fram och tillbaka. Vägen klipp för klipp ovan undviker
det.

## Vad ett Flightradar24-spår kan och inte kan berätta

| | kamerans GPS | Flightradar24 via trim-gpx |
|---|---|---|
| position | flera gånger i sekunden | en punkt med några sekunders mellanrum, raka linjer emellan: en snäv sväng kapas en aning |
| tid | GPS-tid | hela sekunder |
| fart | från GPS:en | uppmätt markfart (ADS-B), hela knop |
| kurs | från GPS:en | uppmätt kurs över marken, hela grader |
| höjd | GPS-höjd | barometrisk, se nedan |

**Höjden** är transponderns barometriska höjd, räknad mot 1013 hPa och inte
korrigerad för dagens QNH
([Flightradar24](https://www.flightradar24.com/blog/inside-flightradar24/understanding-altitude-on-flightradar24/)),
och många transpondrar i småflygplan rapporterar den i steg om 100 ft. På
marken rapporterar Flightradar24 0. Höjden i det återskapade klippet kan därför
skilja sig från kamerans GPS-höjd i klippen före och efter, med ungefär 30 ft
för varje hPa som dagens QNH skiljer sig från 1013.

**På marken och på låg höjd** tar täckningen ofta slut, så taxning och början
av startrullningen kan saknas. Ett klipp som börjar innan Flightradar24 fångar
upp flygplanet ger en `[VARNING]`, och GPX-filen täcker bara den del som
spårades.

**Fart i andra verktyg.** OVRLEY:s GPX-import läser den uppmätta farten. Ett
verktyg som räknar fram farten ur positionerna ser i stället stegen på hela
sekunder.

## Felsökning

| du ser | varför | gör så här |
|---|---|---|
| `[FEL] Fönstret ligger helt utanför spåret.` med ett förslag på `--tz` | kamerans klocka går i en annan tidszon än du angav | använd den föreslagna `--tz` |
| `Varken --tz 0, 1 eller 2 lägger fönstret inuti spåret` | fel flygning eller datum, eller en kameraklocka som går mycket fel | jämför datumet på raden `Källa:` med klippets och kontrollera klockan |
| `[VARNING] Spåret täcker bara …` | Flightradar24 spårade inte den delen: på marken, lågt eller i utkanten av täckningen | inget att göra; OVRLEY visar inga data för resten av klippet |
| `Markfart: … (framräknad ur positionerna)` | indatan hade ingen uppmätt fart | använd Flightradar24:s KML eller CSV |
| `[VARNING] … är kapitel N av en inspelning, men de tidigare kapitlen ligger inte bredvid` | en kapitelfil utan kapitel 1 bredvid sig | lägg inspelningens kapitel i samma mapp, eller lägg till de tidigare kapitlens längd i `--start` |
| `… saknar creation_time` | inte kamerans originalfil | använd `.360`-filen eller ange `--start` |
| `Hittar inte ffprobe` | ffmpeg är inte installerat | `sudo apt install ffmpeg`, eller ange `--start` och `--duration` |
| `Kunde inte läsa …: rad N: …` | en skadad eller annorlunda CSV | kontrollera den raden; rubriken måste ha en kolumn för tid och en för position |
| OVRLEY: *Video could not be synced with activity* | MP4-filens skapandetid saknas eller är en annan | sätt synkoffseten till 0 |

## Ett exempel: GS010132, 17 oktober 2026

MAX2:an fick ingen fix för `GS010132`, 62 sekunder mellan två klipp som hade
GPS. Flightradar24 hade flygningen: 1 526 punkter från 11:36:47Z till
12:35:00Z.

Första försöket gjordes med `--tz 2`, i tron att kameran gick på svensk tid.
Fönstret hamnade på 10:05Z, en och en halv timme före start. Utan `--tz`
hamnade det på 12:05:07–12:06:09Z, mitt i flygningen: 29 punkter med högst
3 s mellanrum, 700–900 ft, en högersväng från 060° till 189° och en markfart
som ökade från 91 till 125 kt.

Framräknad ur positionerna hade farten hoppat mellan 62 och 166 kt. Med
Flightradar24:s uppmätta fart i filen läser OVRLEY:s GPX-import 91 till 125 kt.
