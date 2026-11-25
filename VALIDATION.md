# Validation materielle — lunettes ENGO / ActiveLook

Ce guide valide le protocole filaire sur de vraies lunettes, etape par etape.
Sans cette validation, tout reste simule : c'est LE passage oblige avant le live.

## Pre-requis

- Lunettes chargees et allumees (pres du PC, < 3 m).
- **App officielle ENGO / ActiveLook fermee ou deconnectee** : une seule
  connexion BLE a la fois, sinon le script ne pourra pas se connecter.
- Bluetooth du PC actif. `pip install -r requirements.txt` fait.

## Procedure (5 minutes)

```powershell
cd Z:\Hackatons\OpenBridge\engo-stream-poc
python ble_validate.py
```

Le script scanne, se connecte aux lunettes `A.LooK*`, puis enchaine 7 etapes :
CLEAR, replay de la demo texte officielle, textes a positions variees
(cartographie X/Y), puis un damier 32x32 en imgStream. A chaque etape, mets
les lunettes et reponds a la question (o/n + ce que tu vois).

Tout est journalise dans `validation_log.txt` (trames + observations +
notifications des lunettes) : envoie-moi ce fichier + tes reponses.

## Lecture des resultats

| Observation | Conclusion |
|---|---|
| Etapes 1-2 OK | Connexion + framing FF..AA valides |
| Etapes 3-6 placees correctement | Commande texte 0x37 validee, X/Y confirmes |
| Etape 7 damier visible | imgStream valide, le streaming pixels est ouvert |
| Etape 7 rien, mais 1-6 OK | Texte natif OK, format image a ajuster (candidat B) |
| Rien des l'etape 1 | Connexion refusee / autre revision protocole -> dump GATT |

## Secours : dump GATT

```powershell
python stream.py --transport ble --ble-discover
python stream.py --transport ble --ble-dump <MAC>
```

Compare les UUIDs avec ceux de `protocol.py`. Si differents (ENGO 3 =
revision recente ?), envoie-moi le dump pour adapter.

## Apres validation

- Texte OK -> on branche la chaine traduction live (Whisper -> texte natif).
- Image OK -> on calibre `--throughput` / `--cmd-ms` sur mesures reelles,
  puis streaming hybride en direct.
