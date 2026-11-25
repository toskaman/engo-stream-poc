"""Validation materielle sur vraies lunettes ENGO/ActiveLook (interactif).

Deroule des trames connues puis des variantes, et demande a chaque etape
ce que l'utilisateur voit dans les lunettes. Tout est journalise dans
validation_log.txt (trames envoyees + reponses + notifications TX).

Usage :
  python ble_validate.py                  # scan, choisit A.LooK*, guide pas a pas
  python ble_validate.py --address <MAC>  # adresse connue
  python ble_validate.py --auto           # sans questions (pauses 4s), a observer

Pre-requis : lunettes chargees, allumees, app officielle fermee/deconnectee
(une seule connexion BLE a la fois).
"""

import argparse
import asyncio
import time

import numpy as np

from protocol import (ADV_PREFIX, AL_RX, AL_TX, CLEAR, HELLO_DEMO,
                      build_imgstream_frame, build_text)
from transport_ble import BleGlasses, discover


def ask(question, auto):
    if auto:
        print(f"  [auto] {question} -> pause 4s (observe les lunettes)")
        time.sleep(4)
        return "auto"
    try:
        return input(f"  {question} ")
    except EOFError:
        return "?"


async def main():
    p = argparse.ArgumentParser(description="Validation materielle ENGO")
    p.add_argument("--address", default=None)
    p.add_argument("--auto", action="store_true")
    p.add_argument("--pace-ms", type=float, default=10.0)
    args = p.parse_args()

    log = open("validation_log.txt", "a", encoding="utf-8")
    log.write(f"\n===== session {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")

    address = args.address
    if not address:
        devices = await discover()
        cands = [d for d in devices if (d.name or "").startswith(ADV_PREFIX)]
        if not cands:
            print("Aucune lunette A.LooK* trouvee. Verifie qu'elles sont allumees.")
            return
        address = cands[0].address
        print(f"Lunettes : {cands[0].name} {address}")

    g = BleGlasses(address, pace_ms=args.pace_ms)
    await g.connect(subscribe=True)
    await asyncio.sleep(1.0)

    async def step(name, frame, question):
        print(f"\n>> {name} ({len(frame)} octets)")
        print(f"   TX: {frame.hex(' ')}")
        log.write(f">> {name} TX={frame.hex()}\n")
        log.flush()
        await g.write_frame(frame)
        await asyncio.sleep(1.0)
        ans = ask(question + " (o/n + detail)", args.auto)
        log.write(f"   observe: {ans}\n")
        log.flush()
        return ans

    await step("1. CLEAR", CLEAR, "Ecran efface / noir ?")
    await step("2. HELLO (replay demo officielle)", HELLO_DEMO,
               "Texte 'hello 0' affiche ? Ou ?")
    await step("3. TEXTE perso (20,100)", build_text(20, 100, "LIGNE 1 OK"),
               "'LIGNE 1 OK' visible vers le haut ?")
    await step("4. TEXTE position (150,200)", build_text(150, 200, "POS2"),
               "'POS2' visible en bas a droite ?")
    await step("5. TEXTE (10,40) HAUT", build_text(10, 40, "HAUT"),
               "'HAUT' en haut ?")
    await step("6. TEXTE (10,230) BAS", build_text(10, 230, "BAS"),
               "'BAS' en bas ? (cartographie Y confirmee ?)")

    # Image : damier 32x32 (128 octets) en imgStream candidat A
    chk = (np.indices((32, 32)).sum(axis=0) % 2).astype(bool)
    payload = np.packbits(chk, axis=1).tobytes()
    await step("7. IMAGE damier 32x32 @ (100,100)",
               build_imgstream_frame(100, 100, 32, payload),
               "Damier visible au centre ? (si non : candidat A invalide)")

    print(f"\nTermine : {g.frames} trames, {g.bytes} octets, "
          f"{len(g.rx_log)} notifications TX. Log : validation_log.txt")
    log.write(f"fin: frames={g.frames} bytes={g.bytes} rx={len(g.rx_log)}\n")
    log.close()
    await g.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
