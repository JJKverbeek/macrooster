# MacRooster Installatie

### Installeren

1. Open `MacRooster.dmg`
2. Sleep `MacRooster.app` naar `Applications`
3. Open `MacRooster` vanuit `Applications`
4. Vul je gegevens in
5. Klik op `Installeren`
6. Geef toestemming voor Agenda als macOS daarom vraagt

Daarna werkt de app automatisch op de achtergrond.

## Wat moet je invullen?

- je naam zoals die in het rooster staat
- je e-mailadres
- je app-wachtwoord of mailwachtwoord
- hoe vaak de app moet controleren
- de naam van je agenda
- hoeveel minuten van tevoren je een herinnering wilt

## Gmail

Gebruik bij Gmail een app-wachtwoord en niet je normale wachtwoord.

Je maakt dat hier aan:
- `myaccount.google.com`
- `Beveiliging`
- `2-stapsverificatie`
- `App-wachtwoorden`

## Problemen

### Agenda-toegang geweigerd

Ga naar:
`Systeeminstellingen -> Privacy en beveiliging -> Agenda`

Geef daar toegang aan `MacRooster`.

### Geen rooster gevonden

Controleer:
- of het afzenderfilter klopt
- of het onderwerpfilter klopt
- of de rooster-mail in je inbox staat

## Instellingen later wijzigen

Open gewoon opnieuw:
`Programma's -> MacRooster`

## Voor jou als maker

Release-bestanden maken:

```bash
./build_macrooster_release.sh
```

Bestanden komen hier terecht:
- `release/MacRooster.dmg`

Opmerking:
- voor echt probleemloos installeren op andere Macs heb je uiteindelijk nog Apple code signing en notarization nodig
- zonder notarization kan macOS op andere Macs nog een beveiligingswaarschuwing tonen
