"""Point d'entree : video -> 1-bit -> tuiles -> lunettes (emulees ou reelles).

Exemples :
  python stream.py                                             # demo + emulee, 128x96, delta
  python stream.py --width 288 --height 256 --skip-black --black-cut 0.15
  python stream.py --src 0 --invert auto                       # webcam, fond force au noir
  python stream.py --crop-content --tile 16                    # tuiles fines + bbox contenu
  python stream.py --headless --record emu_out.mp4 --max-frames 150 --time-scale 0
  python stream.py --transport ble --ble-discover               # phase 2 : materiel reel
"""

import argparse
import asyncio
import sys
import time

import cv2

from convert import plan_tiles, to_1bit
from transport_emu import CANVAS_H, CANVAS_W, EmuGlasses


def snap(v, m):
    return max(m, (v // m) * m)


def decide_invert(frame, args):
    """Rendement : l'inversion fait-elle gagner du noir ? Compare les ratios."""
    if args.invert == "on":
        return True
    if args.invert == "off":
        return False
    a = to_1bit(frame, args.width, args.height, args.dither, False,
                args.black_cut, args.thresh_level)
    b = to_1bit(frame, args.width, args.height, args.dither, True,
                args.black_cut, args.thresh_level)
    inv = b.mean() < a.mean()
    print(f"auto-invert : {'ON (fond clair detecte)' if inv else 'OFF (fond deja sombre)'} "
          f"[blancs {a.mean() * 100:.1f}% -> {b.mean() * 100:.1f}%]")
    return inv


def run_emu(args):
    cap = cv2.VideoCapture(int(args.src) if args.src.isdigit() else args.src)
    if not cap.isOpened():
        sys.exit(f"Impossible d'ouvrir la source : {args.src}")
    emu = EmuGlasses(throughput=args.throughput, mtu_payload=args.mtu - 3,
                     cmd_ms=args.cmd_ms, chunk_ms=args.chunk_ms,
                     time_scale=args.time_scale, headless=args.headless,
                     show_scale=args.show_scale, record_path=args.record)
    ox, oy = (CANVAS_W - args.width) // 2, (CANVAS_H - args.height) // 2
    prev = {}
    invert = None
    frames = 0
    t0 = time.time()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:  # boucle sur la video
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            if invert is None:
                invert = decide_invert(frame, args)
            bw = to_1bit(frame, args.width, args.height, args.dither, invert,
                         args.black_cut, args.thresh_level)
            ops, n_total = plan_tiles(bw, args.tile, ox, oy, prev, args.mode,
                                      args.skip_black, args.crop_content)
            sim_before = emu.sim_time
            n_send = n_clear = 0
            for action, ax, ay, tw, th, payload in ops:
                if action == "send":
                    emu.send_tile(ax, ay, tw, th, payload)
                    n_send += 1
                else:
                    emu.clear_tile(ax, ay, tw, th)
                    n_clear += 1
            emu.frames += 1
            frames += 1
            fps = emu.frames / emu.sim_time if emu.sim_time > 0 else 0
            overlay = [
                f"{args.width}x{args.height} {args.mode} inv={invert} blk={args.skip_black}",
                f"sim: {fps:.1f} fps | {emu.sim_time / emu.frames * 1000:.0f} ms/f",
                f"ops: {n_send}S+{n_clear}C/{n_total} | {emu.sim_bytes / 1024:.0f} Ko",
            ]
            if not emu.render(overlay, emu.sim_time - sim_before):
                break
            if frames == 1 or frames % 30 == 0:
                print(f"frame {frames}: {n_send}S+{n_clear}C/{n_total} tuiles, "
                      f"sim_fps={fps:.2f}, sim={emu.sim_time:.1f}s, mur={time.time() - t0:.1f}s")
            if args.max_frames and frames >= args.max_frames:
                break
    finally:
        cap.release()
        s = emu.summary()
        emu.close()
    print("\n=== BILAN (temps simule = prediction materiel reel) ===")
    print(f"frames={s['frames']}  ops={s['tiles']} (dont clears={s['clears']})  "
          f"octets={s['bytes']} ({s['bytes'] / 1024:.1f} Ko)")
    print(f"temps simule={s['sim_time']:.1f}s  -> {s['sim_fps']:.2f} img/s, "
          f"latence ~{s['sim_latency_ms']:.0f} ms/frame")
    print(f"mur={s['wall_time']:.1f}s (source ~{args.src_fps_hint} img/s -> "
          f"afficher 1 frame sur {args.src_fps_hint / s['sim_fps']:.1f})")


def run_ble(args):
    from transport_ble import BleGlasses, discover, dump_services

    async def main():
        if args.ble_discover:
            devices = await discover()
            if devices:
                print("\nRelance avec --ble-dump <MAC> pour voir les services, puis")
                print("--ble-address <MAC> --ble-write-uuid <UUID> pour streamer.")
            return
        if args.ble_dump:
            await dump_services(args.ble_dump)
            return
        if not args.ble_address or not args.ble_write_uuid:
            sys.exit("BLE reel : fournir --ble-address et --ble-write-uuid (voir --ble-discover).")
        cap = cv2.VideoCapture(int(args.src) if args.src.isdigit() else args.src)
        if not cap.isOpened():
            sys.exit(f"Impossible d'ouvrir la source : {args.src}")
        glasses = BleGlasses(args.ble_address, args.ble_write_uuid,
                             mtu_payload=args.mtu - 3, pace_ms=args.chunk_ms)
        await glasses.connect()
        print("NOTE : efface l'ecran des lunettes (commande clear) avant de streamer.")
        ox, oy = (CANVAS_W - args.width) // 2, (CANVAS_H - args.height) // 2
        prev = {}
        invert = None
        t0 = time.time()
        n = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                if invert is None:
                    invert = decide_invert(frame, args)
                bw = to_1bit(frame, args.width, args.height, args.dither, invert,
                              args.black_cut, args.thresh_level)
                ops, n_total = plan_tiles(bw, args.tile, ox, oy, prev, args.mode,
                                          args.skip_black, args.crop_content)
                n_send = 0
                for action, ax, ay, tw, th, payload in ops:
                    if action == "send":
                        await glasses.send_tile(ax, ay, tw, th, payload)
                    else:
                        await glasses.clear_tile(ax, ay, tw, th)
                    n_send += 1
                n += 1
                if n % 10 == 0:
                    print(f"frame {n}: {n_send}/{n_total} ops, {glasses.bytes / 1024:.1f} Ko, "
                          f"{n / (time.time() - t0):.2f} img/s mur")
                if args.max_frames and n >= args.max_frames:
                    break
        finally:
            cap.release()
            await glasses.disconnect()
        print(f"\n{n} frames en {time.time() - t0:.1f}s -> {n / (time.time() - t0):.2f} img/s reelles")

    asyncio.run(main())


def main():
    p = argparse.ArgumentParser(description="Stream video -> lunettes ENGO (POC)")
    p.add_argument("--src", default="demo.mp4", help="fichier video ou index webcam ('0')")
    p.add_argument("--width", type=int, default=128, help="largeur envoyee (multiple de --tile)")
    p.add_argument("--height", type=int, default=96, help="hauteur envoyee (multiple de --tile)")
    p.add_argument("--dither", default="bayer", choices=["bayer", "thresh", "fs"])
    p.add_argument("--thresh-level", type=float, default=0.5,
                   help="seuil du mode thresh (0.2 = garde les gris moyens en aplats)")
    p.add_argument("--mode", default="delta", choices=["full", "delta"])
    p.add_argument("--tile", type=int, default=32, help="taille des tuiles (ex: 16, 32, 64)")
    p.add_argument("--skip-black", action="store_true",
                   help="ne jamais envoyer une tuile noire deja noire (OLED)")
    p.add_argument("--invert", default="off", choices=["off", "on", "auto"],
                   help="fond clair -> fond noir pour maximiser les tuiles sautees")
    p.add_argument("--black-cut", type=float, default=0.0,
                   help="gris sous ce seuil -> noir pur avant dithering (ex: 0.15)")
    p.add_argument("--crop-content", action="store_true",
                   help="restreint au bbox du contenu non-noir")
    p.add_argument("--throughput", type=int, default=15000, help="octets/s BLE simules")
    p.add_argument("--mtu", type=int, default=247)
    p.add_argument("--cmd-ms", type=float, default=30.0, help="overhead firmware par commande")
    p.add_argument("--chunk-ms", type=float, default=5.0, help="overhead par chunk BLE")
    p.add_argument("--time-scale", type=float, default=1.0, help="1=reel, 0=instantane")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--show-scale", type=int, default=2)
    p.add_argument("--record", default=None, help="enregistre la vue lunettes (mp4)")
    p.add_argument("--max-frames", type=int, default=0)
    p.add_argument("--src-fps-hint", type=float, default=15.0)
    p.add_argument("--transport", default="emu", choices=["emu", "ble"])
    p.add_argument("--ble-discover", action="store_true")
    p.add_argument("--ble-dump", default=None, metavar="MAC")
    p.add_argument("--ble-address", default=None)
    p.add_argument("--ble-write-uuid", default=None)
    args = p.parse_args()
    # Aligne sur 8px (packbits), pas sur la tuile : les bords partiels sont
    # geres (ex: 304 = 9 tuiles de 32 + 1 bord de 16).
    args.width, args.height = snap(args.width, 8), snap(args.height, 8)
    args.width, args.height = min(args.width, CANVAS_W), min(args.height, CANVAS_H)
    print(f"Config : {args.width}x{args.height} mode={args.mode} tile={args.tile} "
          f"dither={args.dither} skipblk={args.skip_black} inv={args.invert} "
          f"blkcut={args.black_cut} crop={args.crop_content}")
    if args.transport == "ble":
        run_ble(args)
    else:
        run_emu(args)


if __name__ == "__main__":
    main()
