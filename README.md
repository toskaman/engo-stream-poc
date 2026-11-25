# ENGO Stream POC — video vers HUD ActiveLook via imgStream

POC : convertir un flux video en bitmap 1-bit a basse resolution et le
pousser vers des lunettes ENGO/ActiveLook en BLE (commande `imgStream 0x44`).

Scope : **animations uniquement** (contenus epars, HUD, sous-titres).
La video dense plein ecran reste hors de portee du BLE (cf. mesures).

## Lancer la demo emulee (sans lunettes)

```powershell
cd Z:\Hackatons\OpenBridge\engo-stream-poc
pip install -r requirements.txt
python demo_gen.py
python stream.py
```

Une fenetre montre en temps reel ce que verraient les lunettes (canvas 304x256),
avec fps simule, latence et tuiles envoyees. `q` pour quitter.

## Variantes utiles

```powershell
python stream.py --width 152 --height 128 --mode full   # grand mais lent
python stream.py --width 96 --height 64                 # petit mais fluide
python stream.py --src 0                                # webcam en direct
python stream.py --dither fs                            # Floyd-Steinberg (plus beau, plus lent)
python stream.py --headless --record emu_out.mp4 --max-frames 150 --time-scale 0
# Plein ecran + contenu epars (OLED) :
python sparse_gen.py
python stream.py --src sparse_dark.mp4 --width 288 --height 256 --skip-black --black-cut 0.15
# Contenu clair (auto-inversion fond -> noir) :
python stream.py --src sparse_light.mp4 --width 288 --height 256 --skip-black --black-cut 0.15 --invert auto
# Resolution native max (304x256) :
python stream.py --width 304 --height 256 --dither thresh --skip-black --black-cut 0.15
# Compromis detail/vitesse : --thresh-level 0.5 (silhouettes, rapide) vs 0.2 (gris gardes, lent)
```

## Phase 2 : lunettes reelles

1. `python stream.py --transport ble --ble-discover` → liste les appareils.
2. `python stream.py --transport ble --ble-dump <MAC>` → dump GATT.
3. Valider le format imgStream (cf. `protocol.py`, source brevet EP4090057).
4. Streamer : `--transport ble --ble-address <MAC> --ble-write-uuid <UUID>`.

## Fichiers

- `stream.py` : point d'entree pixels.
- `hybrid_demo.py` : demo hybride (pixels + texte natif 0x37).
- `ble_validate.py` : validation materielle interactive (voir VALIDATION.md).
- `convert.py` : downscale + dithering + tuiles + skip-black + crop.
- `protocol.py` : UUIDs GATT + trames clear/texte/imgStream.
- `transport_emu.py` : emulateur lunettes + simulation debit BLE.
- `transport_ble.py` : transport BLE reel (bleak).
- `demo_gen.py` / `sparse_gen.py` : videos de test.
