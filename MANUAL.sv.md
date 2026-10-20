# Manual: komplettera ett klipps GPS-spår

🇬🇧 [English](MANUAL.md) · [Tillbaka till README](README.sv.md)

Ibland spelar GoPro MAX2 in utan GPS-fix under en del av ett klipp, eller hela.
Den slogs på strax innan, eller satt för långt in i cockpit för att se himlen.
Telemetrin ur den `.360`-filen saknar då positioner, och OVRLEY har ingenting
att rita: overlayen står still, eller visar ingenting alls.

Kamerans eget spår är de bästa data som finns, tio punkter i sekunden, så
`trim_gpx.py --check` behåller det där det finns och fyller bara luckorna: från
en SkyDemon-logg av flygningen om du har en, annars från Flightradar24.

- [Det här behöver du](#det-här-behöver-du)
- [Flödet](#flödet)
- [1. Extrahera kamerans GPX som vanligt](#1-extrahera-kamerans-gpx-som-vanligt)
- [2. Lägg flygningens spår bredvid](#2-lägg-flygningens-spår-bredvid)
- [3. Kör kontrollen](#3-kör-kontrollen)
- [4. Fyll luckorna](#4-fyll-luckorna)
- [5. Kontrollera resultatet](#5-kontrollera-resultatet)
- [6. OVRLEY](#6-ovrley)
- [7. Tillbaka in i filmen](#7-tillbaka-in-i-filmen)
- [Klippa ett spår för hand](#klippa-ett-spår-för-hand)
- [Kamerans klocka](#kamerans-klocka)
- [Vad ifyllda data kan och inte kan berätta](#vad-ifyllda-data-kan-och-inte-kan-berätta)
- [Felsökning](#felsökning)
- [Två exempel från 17 oktober 2026](#två-exempel-från-17-oktober-2026)

## Det här behöver du

**Verktyg:** `trim_gpx.py` ([installation](README.sv.md#installation)),
ffprobe (`sudo apt install ffmpeg` i WSL), gpsbabel (`sudo apt install
gpsbabel`, för en GPX-kopia av Flightradar24-exporten), gopro-telemetry-tool
för kamerans GPX, och OVRLEY. Klippens `.360`-filer måste finnas till hands, på
kortet eller som kopia: deras `creation_time` och längd talar om vad varje GPX
ska täcka.

**Ett spår av flygningen att fylla från**, i den här ordningen:

1. **SkyDemon.** Om SkyDemon spelade in flygningen exporterar du loggen som GPX.
   Den har surfplattans GPS-höjd och uppmätt markfart, med en punkt med några
   sekunders mellanrum (var 5:e sekund i loggen som det här utvecklades med).
2. **Flightradar24.** Det fungerar bara om Flightradar24 spårade flygningen med
   positioner:
   - Flygplanets transponder måste vara på och sända **ADS-B**: Mode S extended
     squitter med en GNSS-källa för positionen. Det är därifrån Flightradar24
     får positioner, fart och kurs.
   - Utan ADS-B kan Flightradar24 bara positionera ett flygplan med MLAT, genom
     att tidsmäta transponderns svar vid tre eller fler mottagare. I större
     delen av Europa fungerar det över ungefär 5 000–10 000 ft
     ([Flightradar24](https://www.flightradar24.com/how-it-works/mlat)). För en
     VFR-flygning på några tusen fot betyder ingen ADS-B alltså inget spår.
   - En mottagare måste höra flygplanet. Lågt och på marken har täckningen hål.
     En egen mottagare nära hemmafältet hjälper.
   - Du måste kunna ladda ner flygningen. KML- och CSV-export finns för Silver,
     Gold och Business, med 90 dagars, ett års respektive tre års historik
     ([Flightradar24](https://www.flightradar24.com/blog/inside-flightradar24/using-the-new-flightradar24-kml-and-csv-export-tools/)).
     Den som har en Flightradar24-mottagare får den kostnadsfria Contributor
     Plan, och det är med den som underhållaren laddar ner. Ladda ner
     flygningen medan den fortfarande finns inom din plans historik.

**Kamerans klocka bör gå rätt** på några sekunder när. `--check` visar hur
mycket den går fel, för varje klipp som har fix
([kamerans klocka](#kamerans-klocka)).

## Flödet

```
 kameran  GS010130.360 ──gopro-telemetry-tool──► GS010130.gpx  (kamerans egen GPS)
                                                      │
 SkyDemon-logg (GPX) ─────────┐                       │
 Flightradar24 (KML eller CSV) ┴─► trim_gpx.py --check .  ◄── creation_time, längd (.360)
                                                      │
                                                      ▼
                     GS010130.gpx, komplett (originalet sparat som GS010130.gpx.orig)
                                                      │
 GoPro Player  GS010130.mp4 ─────────────────────────►┤
                                                      ▼
                         OVRLEY (MP4 + GPX) ──► GS010130_ovr.mp4
                                                      │
               xfade_concat.py → titles_in_360.py → inject360-inplace (sist)
```

## 1. Extrahera kamerans GPX som vanligt

Extrahera telemetrin med gopro-telemetry-tool till flygningens mapp: en
`GS010130.gpx` per klipp. Här ändras ingenting; `--check` arbetar med de här
filerna.

## 2. Lägg flygningens spår bredvid

Lägg SkyDemon-loggen och/eller Flightradar24-exporten av flygningen i samma
mapp. `--check` letar där efter spår som täcker det som saknas. (Ett spår som
ligger någon annanstans anger du med `--fill`, eller dess mapp med `--search`.)

**Från Flightradar24:** logga in på flightradar24.com och sök på flygplanets
registrering. Leta upp flygningen i listan över tidigare flygningar på
flygplanets sida och tryck på **KML** (eller **CSV**). Döp filen efter din
flygning och behåll Flightradar24:s flyg-ID, t.ex. `fl02_42294bf5.kml`: dagens
andra flygning, Flightradar24-flygning `42294bf5`. KML och CSV ger samma
resultat, och en gpsbabel-konvertering av KML-filen fungerar också. Ligger
flera av dem i mappen erbjuds de en gång.

`trim_gpx.py` sparar också exporten som GPX bredvid, `fl02_42294bf5.gpx`, för
program som vill ha GPX. gpsbabel gör den, från CSV-filen om du laddat ner
båda (då följer farten och kursen med). Skriptet gör det varje gång det läser
exporten: vid varje `--check` av mappen, oavsett om något saknas, och vid
klippning. Det gör om den bara när exporten är nyare, och aldrig över en GPX
som gpsbabel inte gjort. Så länge KML/CSV-filen ligger bredvid erbjuds den
GPX-filen inte för ifyllnad. För hand tar KML-filen:

```bash
gpsbabel -i kml -f fl02_42294bf5.kml -x nuketypes,tracks,routes -x transform,trk=wpt,del -o gpx -F fl02_42294bf5.gpx
```

Ett enkelt `gpsbabel -i kml -f … -o gpx -F …` ger de tidsstämplade punkterna
som waypoints och rutten som ett spår utan tider; de två filtren gör ett
tidsstämplat spår av punkterna. CSV-filen behöver en xcsv-stil för sitt
citerade `"lat,lon"`: den finns som `FR24_CSV_STYLE` i `trim_gpx.py`.

**Från SkyDemon:** exportera flygningens logg som GPX, t.ex. `SD_ESTT-ESTL.gpx`.
SkyDemon skriver sitt namn i filen, och det är så den känns igen.

## 3. Kör kontrollen

```bash
cd /sökväg/till/flygningen
trim_gpx.py --check . --video-dir /mnt/e/DCIM/100GOPRO --lang sv
```

`--video-dir` talar om var klippens `.360`-filer ligger. Utan den letas de
efter bredvid GPX-filerna. Hittas bara en `.mp4` där används den med en
varning: dess `creation_time` stämmer bara om den är kamerans.

Varje klipp får en rad:

```
Kontrollerar 2 klipp, videor i /mnt/e/DCIM/100GOPRO:
  GS010130.gpx  saknas     63.1 s av 203.093 s: 10:00:27Z – 10:01:30Z · kamerans klocka +0.03 s
  GS010132.gpx  ingen GPS  62.208 s
```

- **komplett**: kameran har data för hela klippet; filen lämnas orörd.
- **saknas**: sträckor utan data, längre än 2 s (`--max-gap`).
- **ingen GPS**: kameran hade ingen fix alls under klippet.
- **fel**: klippet kunde inte kontrolleras, t.ex. hittades ingen `.360`.
- **kamerans klocka**: GPS-tiden vid klippets första bildruta minus dess
  `creation_time`. Eftersom `creation_time` anges i hela sekunder betyder allt
  under en sekund att klockan går rätt.

`--dry-run` stannar här och ändrar ingenting. (`--lang sv` behövs inte om du
har `GOPRO_LANG=sv` satt.)

## 4. Fyll luckorna

För varje klipp med luckor erbjuder `--check` de spår som täcker dem, en
SkyDemon-logg före ett Flightradar24-spår:

```
GS010130.gpx: saknar 10:00:27Z – 10:01:30Z (63.1 s av 203.093 s)
  Fyll från:
    1  fl02_42294bf5.gpx  Flightradar24  täcker 63.1 s av 63.1 s
  Välj 1–1 (Enter = 1), en annan fil, eller n för att lämna luckan:
  ✓ 63.1 s från fl02_42294bf5.gpx (30 punkter); matchat mot kameran: höjd +182 ft, position 3 m
  ✅ GS010130.gpx uppdaterad: 1401 kamerapunkter + 30 ifyllda (originalet: GS010130.gpx.orig)
```

Tryck Enter för det första, ange numret på ett annat, eller skriv sökvägen till
en fil som inte hittades (en Windows-sökväg som `C:\Users\…\logg.gpx` fungerar
i WSL). `n` lämnar luckan. Täcker ett spår bara en del av en lucka frågar den
igen om resten.

`--yes` tar det bästa spåret utan att fråga, och `--fill SPÅR` anger spåret
själv, även när ingenting frågas (i ett skript, till exempel).

Det här händer med filen:

- **Kamerans punkter lämnas som de är.** Bara de sträckor som saknas fylls i,
  och varje ifylld punkt anger sin källa i `<src>`.
- **Fyllnaden passas ihop med kameran.** Vid varje skarv flyttas den så att den
  möter kamerans position och GPS-höjd, mätt över de 10 sekunderna kameradata
  bredvid skarven, så att höjden inte gör något hopp och farten inget ryck.
  Här låg Flightradar24:s barometriska höjd 182 ft under kamerans GPS-höjd.
- **Ett klipp utan egen fix** har ingen skarv. Det får höjdskillnaden från
  grannklippens GPX i samma mapp (upp till 30 minuter bort), så att höjden
  följer på klippen före och efter i filmen. Utan grannar används källans egen
  höjd, och utskriften säger det.
- **Filen uppdateras på plats**, så OVRLEY och gopro-max-gpx-pipeline hittar den
  under det vanliga namnet. Kamerans original sparas som `GS010130.gpx.orig`.
  `-o` skriver någon annanstans i stället.
- **Uppmätt fart och kurs** från källan läggs i varje ifylld punkt, och OVRLEY
  visar dem i stället för att räkna fram farten ur positionerna.
- **GPX-filen täcker alltid hela klippet.** Täcker inget spår klippets början
  (eller slut), står en punkt på första (eller sista) bildrutan kvar på
  närmaste position, märkt `<src>hold</src>`, utan fart och kurs. Då visar
  OVRLEY GPX-filen lika lång som videon, och synkoffseten blir 0. Den räknas
  inte som data: luckan rapporteras fortfarande, och fylls vid en senare
  körning om ett spår för den dyker upp.

  ```
    saknas fortfarande: 11:36:08Z – 11:36:47Z (39.0 s)
    ✅ GS010131.gpx uppdaterad: 3179 kamerapunkter + 10 ifyllda (originalet: GS010131.gpx.orig)
    GPX-filen täcker ändå hela klippet: under 11:36:08Z – 11:36:47Z står den kvar på närmaste position (inga data).
  ```

## 5. Kontrollera resultatet

Kör kontrollen igen. Ett ifyllt klipp räknas nu som komplett och säger varifrån
fyllnaden kom:

```
  GS010130.gpx  komplett   203.093 s, största glapp 3.0 s; 63.1 s ifyllt tidigare från fl02_42294bf5.gpx
  GS010132.gpx  komplett   62.208 s, största glapp 3.0 s; 62.2 s ifyllt tidigare från fl03_4229ad6f.kml
```

Varje klipp fylldes från sin egen flygnings export: bara spår som täcker den
tid som saknas erbjuds.

GPX-filen kan öppnas i Google Earth, GPXSee eller liknande, och den ifyllda
sträckan jämföras med videon: en sväng, en stigning, banan vid landning.

För att fylla igen från ett annat spår: `--refill` slänger den tidigare
fyllnaden och behåller kamerans punkter. För att gå tillbaka till kamerans
original: `mv GS010130.gpx.orig GS010130.gpx`.

## 6. OVRLEY

1. Importera det stitchade klippet, GoPro Players MP4 (t.ex. `GS010130.mp4`),
   och dess GPX som aktivitet, som för vilket klipp som helst.
2. **Synk.** OVRLEY:s automatiska synk jämför videons skapandetid med
   GPX-filen. Den kompletterade GPX-filen börjar på klippets första bildruta
   (där den står kvar om inget täckte början), så synkoffseten landar på 0 s.
   Säger OVRLEY *Video could not be synced with
   activity* sätter du synkoffseten till 0 för hand.
3. Finjustera om en sväng i bilden och på kartan inte stämmer överens.
   Synkoffseten kan nudgas en sekund i taget.
4. Rendera som för de andra klippen: `GS010130_ovr.mp4`.

OVRLEY:s GPX-import läser den uppmätta farten ur varje ifylld punkt och
använder den i stället för att räkna fram farten ur positionerna (kontrollerat
mot OVRLEY:s källkod, commit `13c3f41`). Därför får OVRLEY klippets egen GPX och
inte GPX-kopian av Flightradar24-exporten: gpsbabel skriver farten som
`<speed>`, och den läser inte OVRLEY. Dess NVIDIA-väg skriver 8-bitarsvideo,
även från GoPro Players 10-bitsexport, så `_ovr`-klippen passar ihop med
varandra. Lägg inte en 10-bitsexport i samma körning av `xfade_concat.py` som
`_ovr`-klipp, för då kraschar den vid första övergången med `Invalid output
format nv12 for hwframe download`.

## 7. Tillbaka in i filmen

```powershell
python $HOME\bin\xfade_concat.py -o GS00131-134_ovr.mp4 GS010131_ovr.mp4 GS010132_ovr.mp4 GS010133_ovr.mp4 GS010134_ovr.mp4
```

Sedan `titles_in_360.py`, och `inject360-inplace` sist.

**Med gopro-max-gpx-pipeline i stället** (en sammanslagen video, telemetrin som
SRT): den kompletterade GPX-filen behåller sitt namn, så `gpx_to_dji_srt.py
--pairs-from-basenames 'GS0*.gpx'` tar med den. SRT-filen har dock ingen fart,
så OVRLEY räknar fram den ur positionerna där, och över en Flightradar24-sträcka
hoppar den fram och tillbaka med de hela sekunderna. Vägen klipp för klipp ovan
undviker det.

## Klippa ett spår för hand

När det inte finns någon kamera-GPX alls kan ett spår klippas till ett klipp
direkt:

```bash
trim_gpx.py fl03_4229ad6f.kml GS010132.gpx --video /mnt/e/DCIM/100GOPRO/GS010132.360 --lang sv
```

```
Källa:    1526 tidsstämplade punkter, 2026-10-17 11:36:47Z – 12:35:00Z
Video:    GS010132.360: creation_time 2026-10-17T12:05:07Z, längd 62.208 s
Fönster:  2026-10-17 12:05:07Z – 12:06:09Z (62.208 s)
I fönstret: 29 källpunkter, största glapp mellan punkter 3 s
Höjd:     213–274 m (700–900 ft)
Markfart: 91–125 kt (uppmätt i källan, skrivs med)
Kurs:     060° → 189°

✅ Sparade 30 punkter → GS010132.gpx
```

Utan `--video` anger du `--start` och `--duration` (från `ffprobe -v error
-show_entries format=duration:format_tags=creation_time -of default=nw=1
GS010132.360`). För kapitel 2 och framåt av en lång inspelning kontrollerar
`--video` om kapitlets `creation_time` är dess egen start eller hela
inspelningens (genom att jämföra med kapitel 1 i samma mapp) och lägger till de
tidigare kapitlens längd vid behov. Ett klippt spår får ingen höjdmatchning:
det kräver `--check` och kamerans GPX, även en tom.

## Kamerans klocka

`creation_time` är kamerans klocka, och filen märker den alltid som UTC (`Z`),
vad klockan än var inställd på. gopro-telemetrys första GPX-punkt är daterad
till klippets första bildruta i GPS-tid, så för varje klipp med fix kan
`--check` jämföra de två: det är kolumnen `kamerans klocka`. Den MAX2 som det
här utvecklades med skriver UTC och går rätt inom den sekund som
`creation_time` anger.

En kamera som går på lokal tid syns som en klocka som går en eller två timmar
fel. För ett klipp med fix följer fönstret då GPS-tiden, med en varning (sätt
OVRLEY:s synkoffset till 0 för det klippet). Ett klipp utan fix kan inte
kontrolleras så: ange `--tz 2` för svensk sommartid, `--tz 1` för vintertid.
När du klipper ett spår för hand får ett fönster som missar spåret ett förslag:

```
Fönster:  2026-10-17 10:05:07Z – 10:06:09Z (62.208 s)
[FEL]     Fönstret ligger helt utanför spåret.
          Utan --tz hamnar fönstret 12:05:07Z – 12:06:09Z, helt inuti spåret.
```

En klocka som går några sekunder fel syns som en overlay som ligger lite före
eller efter bilden. I 100 kt är en sekund ungefär 50 m. Justera det i OVRLEY.

## Vad ifyllda data kan och inte kan berätta

| | kamerans GPS | SkyDemon | Flightradar24 |
|---|---|---|---|
| position | 10 gånger i sekunden | en punkt med några sekunders mellanrum | en punkt med några sekunders mellanrum |
| tid | GPS-tid | hela sekunder | hela sekunder |
| fart | från GPS:en | uppmätt, m/s | uppmätt markfart (ADS-B), hela knop |
| kurs | från GPS:en | — (OVRLEY räknar fram den) | uppmätt kurs över marken, hela grader |
| höjd | GPS | GPS | barometrisk, se nedan |

Mellan punkterna går det ifyllda spåret i raka linjer, så en snäv sväng kapas
en aning.

**Flightradar24:s höjd** är transponderns barometriska höjd, räknad mot
1013 hPa och inte korrigerad för dagens QNH
([Flightradar24](https://www.flightradar24.com/blog/inside-flightradar24/understanding-altitude-on-flightradar24/)),
och många transpondrar i småflygplan rapporterar den i steg om 100 ft.
`--check` flyttar den till kamerans GPS-höjd vid skarvarna; ett klippt spår
behåller den som den är. Nära marken betyder Flightradar24:s 0 "lågt", inte "på
marken". I båda exempelflygningarna gick höjden direkt mellan 200 och 0 ft och
visade aldrig 100. Vid en landning låg kamerans GPS fortfarande ungefär 200 ft
över banan när Flightradar24 gick till 0, 20 s före sättningen. En ifylld
sträcka med 0-ft-punkter får därför en och samma höjd, 0 plus skarvens skillnad
(t.ex. 238 ft). Det stämmer ungefär strax efter start och före landning, och är
för högt på banan.

**På marken och på låg höjd** tar Flightradar24:s täckning ofta slut, så taxning
och startrullning kan saknas: på marken måste en mottagare finnas inom ett par
mil, utan något i vägen. I båda exempelflygningarna började spåret först vid
ungefär 75 kt, runt lättningen; i den ena hade rullningen börjat 33 s tidigare.
Det som inget spår täcker förblir saknat, och `--check` säger det.

## Felsökning

| du ser | varför | gör så här |
|---|---|---|
| `saknas` men ingenting erbjuds | inget spår bredvid klippen täcker luckan | lägg SkyDemon-loggen eller Flightradar24-exporten i mappen, eller ange den med `--fill` |
| `… har inga data för den tid som saknas.` | det valda spåret är från en annan flygning eller tid | välj ett annat, eller kontrollera datumet och klippets `--video-dir` |
| `saknas fortfarande: …` | spåren täcker bara en del av luckan (mark, låg höjd, utkanten av täckningen) | lägg till ett spår till, eller `n` för att lämna det; GPX-filen täcker ändå klippet |
| OVRLEY visar GPX-filen kortare än videon | en GPX från 1.2.0 vars början eller slut inte gick att fylla | kör `--check` igen med 1.2.1 eller senare: den lägger till punkten som står kvar |
| `höjden inte matchad` | ett klipp utan fix och utan grannklippens kamera-GPX i mappen | lägg grannklippens GPX i mappen och kör med `--refill` |
| `fel  ingen video GS010130.360 eller .mp4` | `.360`-filen hittades inte | ange `--video-dir` |
| `[VARNING] … tiden tas från GS010130.mp4, inte kamerans .360` | bara en `.mp4` hittades | ange `--video-dir` med `.360`-filerna |
| `[VARNING] … kamerans klocka går … fel mot GPS-tiden` | kamerans klocka gick fel (eller på lokal tid) | inget för GPX-filen; sätt OVRLEY:s synkoffset till 0 |
| `hittar inte ffprobe` | ffmpeg är inte installerat | `sudo apt install ffmpeg` |
| `[VARNING] Hittar inte gpsbabel …` | gpsbabel är inte installerat; bara GPX-kopian av Flightradar24-exporten saknas | `sudo apt install gpsbabel` |
| `[VARNING] … är inte gjord av gpsbabel, så … sparas inte som GPX över den.` | en egen GPX har exportens namn | döp om en av dem |
| klippning: `[FEL] Fönstret ligger helt utanför spåret.` med ett förslag på `--tz` | kamerans klocka går i en annan tidszon än du angav | använd den föreslagna `--tz` |
| klippning: `Kunde inte läsa …: rad N: …` | en skadad eller annorlunda CSV | kontrollera den raden; rubriken måste ha en kolumn för tid och en för position |
| OVRLEY: *Video could not be synced with activity* | MP4-filens skapandetid saknas eller är en annan | sätt synkoffseten till 0 |

## Två exempel från 17 oktober 2026

**GS010130: kameran väntade en minut på fix.** Klippet går 10:00:27–10:03:50Z,
inflygningen och landningen, men kamerans GPS börjar först 10:01:30.
gopro-telemetrys platshållare för första bildrutan låg på den första fixens
position, så OVRLEY stod still i 63 sekunder. Platshållaren visade också att
kamerans klocka gick rätt: 10:00:27.026 i GPS-tid mot en `creation_time` på
10:00:27 (hela sekunder). `--check` fyllde de 63 sekunderna från flygningens
Flightradar24-export (30 punkter). Bredvid skarven låg kamerans GPS-höjd 182 ft
över Flightradar24:s barometriska, och positionerna stämde inom 3 m, så
fyllnaden flyttades med så mycket: höjden går 905, 911, 914 ft över skarven,
och farten framräknad ur positionerna 76, 75 kt.

**GS010132: ingen fix alls.** Kamerans GPX var tom. `--check` fyllde hela
62 sekunderna från Flightradar24-exporten. Med GPX-filerna för klippen före och
efter i samma mapp matchas höjden mot deras GPS-höjd; utan dem är det
Flightradar24:s barometriska höjd, och utskriften säger det.
