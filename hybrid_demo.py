"""Demo hybride : graphique en pixels + sous-titres en texte natif.

Scenario synthetique (aucune video requise), resolution native 304x256 :
- une balle rebondissante en PIXELS (sparse, delta + skip-black) ;
- un titre fixe + des sous-titres en TEXTE NATIF 0x37 (1 commande chacun).

But : mesurer le gain de l'hybride vs tout-pixels (cf. stream.py sur
sparse_dark.mp4 : 4.36 img/s) et valider l'architecture cible :
traduction live -> texte natif, retour visuel -> pixels epars.
"""

import argparse
import math
import time

import numpy as np

from convert import plan_tiles
from transport_emu import CANVAS_H, CANVAS_W, EmuGlasses

SUBS = [
    (0.0, 3.0, "Bonjour, ceci est un sous-titre."),
    (3.0, 6.0, "Envoye en texte natif, pas en pixels."),
    (6.0, 9.0, "Cout : ~50 octets par phrase."),
    (9.0, 12.0, "La balle, elle, est en pixels."),
]
SUB_BAND = (0, 208, 304, 40)  # x, y, w, h
BALL_R = 15


def ball_bitmap(t, seconds):
    bw = np.zeros((CANVAS_H, CANVAS_W), dtype=bool)
    bx = int(CANVAS_W / 2 + (CANVAS_W / 2 - 30) * math.sin(2 * math.pi * t / seconds * 3))
    by = int(100 + 70 * abs(math.sin(2 * math.pi * t / seconds * 5)))
    yy, xx = np.ogrid[:CANVAS_H, :CANVAS_W]
    bw[(yy - by) ** 2 + (xx - bx) ** 2 <= BALL_R ** 2] = True
    return bw


def sub_at(t):
    for t0, t1, s in SUBS:
        if t0 <= t < t1:
            return s
    return SUBS[-1][2]


def main():
    p = argparse.ArgumentParser(description="Demo hybride pixels + texte natif")
    p.add_argument("--seconds", type=float, default=12.0)
    p.add_argument("--src-fps", type=float, default=15.0)
    p.add_argument("--tile", type=int, default=32)
    p.add_argument("--throughput", type=int, default=15000)
    p.add_argument("--mtu", type=int, default=247)
    p.add_argument("--cmd-ms", type=float, default=30.0)
    p.add_argument("--chunk-ms", type=float, default=5.0)
    p.add_argument("--time-scale", type=float, default=1.0)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--show-scale", type=int, default=2)
    p.add_argument("--record", default=None)
    args = p.parse_args()

    emu = EmuGlasses(throughput=args.throughput, mtu_payload=args.mtu - 3,
                     cmd_ms=args.cmd_ms, chunk_ms=args.chunk_ms,
                     time_scale=args.time_scale, headless=args.headless,
                     show_scale=args.show_scale, record_path=args.record)
    emu.clear_all()
    emu.send_text(8, 20, "HYBRIDE: balle=px, sous-titres=txt")
    prev = {}
    cur_sub = None
    n = int(args.seconds * args.src_fps)
    t0 = time.time()
    try:
        for i in range(n):
            t = i / args.src_fps
            sub = sub_at(t)
            if sub != cur_sub:  # sous-titre : 1 clear + 1 texte natif
                emu.clear_tile(*SUB_BAND)
                emu.send_text(8, 232, sub)
                cur_sub = sub
            bw = ball_bitmap(t, args.seconds)
            ops, n_total = plan_tiles(bw, args.tile, 0, 0, prev, "delta", True, False)
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
            fps = emu.frames / emu.sim_time
            overlay = [
                "HYBRIDE 304x256 px+titre natif",
                f"sim: {fps:.1f} fps | {emu.sim_time / emu.frames * 1000:.0f} ms/f",
                f"px:{n_send}S+{n_clear}C txt:{emu.texts} | {emu.sim_bytes / 1024:.1f} Ko",
            ]
            if not emu.render(overlay, emu.sim_time - sim_before):
                break
            if i % 45 == 0:
                print(f"t={t:.1f}s sub='{sub[:30]}...' px={n_send}S+{n_clear}C "
                      f"sim_fps={fps:.2f}")
    finally:
        s = emu.summary()
        emu.close()
    print("\n=== BILAN HYBRIDE ===")
    print(f"frames={s['frames']}  tuiles_px={s['tiles']}  textes={s['texts']}  "
          f"octets={s['bytes']} ({s['bytes'] / 1024:.1f} Ko)")
    print(f"temps simule={s['sim_time']:.1f}s -> {s['sim_fps']:.2f} img/s, "
          f"latence ~{s['sim_latency_ms']:.0f} ms/frame (mur={s['wall_time']:.1f}s)")


if __name__ == "__main__":
    main()
