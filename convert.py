"""Conversion frame video -> bitmap 1-bit + decoupage en tuiles."""

import cv2
import numpy as np

BAYER4 = np.array([
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
], dtype=np.float32) / 16.0


BLACK = object()  # sentinelle : tuile connue comme noire a l'ecran


def to_1bit(bgr, w: int, h: int, mode: str = "bayer", invert: bool = False,
            black_cut: float = 0.0, thresh_level: float = 0.5):
    """Redimensionne en w×h et binarise. Retourne un tableau bool (h, w).

    invert : fond clair -> fond noir (maximise les tuiles noires sur OLED).
    black_cut : les gris sous ce seuil deviennent noir pur AVANT dithering
                (tue le bruit de dither dans les zones sombres -> tuiles skippables).
    """
    small = cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    if invert:
        gray = 1.0 - gray
    if black_cut > 0:
        gray = np.where(gray < black_cut, 0.0, gray)
    if mode == "thresh":
        return gray > thresh_level
    if mode == "fs":
        return _floyd_steinberg(gray)
    # Bayer 4x4 ordonne (rapide, temps reel)
    t = BAYER4[np.arange(h)[:, None] % 4, np.arange(w)[None, :] % 4]
    return gray > t


def _floyd_steinberg(g):
    g = (g * 255.0).copy()
    h, w = g.shape
    out = np.zeros((h, w), dtype=bool)
    for y in range(h):
        for x in range(w):
            old = g[y, x]
            new = 255.0 if old >= 128 else 0.0
            out[y, x] = new > 0
            err = old - new
            if x + 1 < w:
                g[y, x + 1] += err * 7 / 16
            if y + 1 < h:
                if x > 0:
                    g[y + 1, x - 1] += err * 3 / 16
                g[y + 1, x] += err * 5 / 16
                if x + 1 < w:
                    g[y + 1, x + 1] += err * 1 / 16
    return out


def extract_tiles(bw, tile: int = 32):
    """Decoupe le bitmap en tuiles (tx, ty, tw, th, payload_packed).

    w et h doivent etre des multiples de `tile` (garanti par stream.py).
    """
    h, w = bw.shape
    out = []
    for ty in range(0, h, tile):
        for tx in range(0, w, tile):
            t = bw[ty:ty + tile, tx:tx + tile]
            th, tw = t.shape
            packed = np.packbits(t, axis=1).tobytes()
            out.append((tx, ty, tw, th, packed))
    return out


def plan_tiles(bw, tile, ox, oy, prev, mode="delta", skip_black=False, crop=False):
    """Planifie les operations d'envoi pour une frame.

    Retourne (ops, n_total) avec ops = ('send'|'clear', ax, ay, tw, th, payload|None).
    - mode='delta' : ne renvoie que les tuiles modifiees.
    - skip_black : ne renvoie jamais une tuile noire deja noire a l'ecran ;
      une tuile qui DEVIENT noire recoit un 'clear' (pas cher : commande seule).
    - crop : restreint au bbox du contenu non-noir ; les tuiles sorties
      du cadre sont 'clear' (evite les pixels fantomes).
    Hypothese : ecran efface au depart (cle manquante dans prev = noir).
    """
    h, w = bw.shape
    if crop:
        ys, xs = np.nonzero(bw)
        if xs.size == 0:
            regions = []
        else:
            x0 = (int(xs.min()) // tile) * tile
            y0 = (int(ys.min()) // tile) * tile
            x1 = min(w, (int(xs.max()) // tile + 1) * tile)
            y1 = min(h, (int(ys.max()) // tile + 1) * tile)
            regions = [(x0, y0, x1, y1)]
    else:
        regions = [(0, 0, w, h)]
    ops = []
    current = set()
    n_total = 0
    for rx0, ry0, rx1, ry1 in regions:
        for ty in range(ry0, ry1, tile):
            for tx in range(rx0, rx1, tile):
                t = bw[ty:ty + tile, tx:tx + tile]
                th, tw = t.shape
                key = (ox + tx, oy + ty)
                current.add(key)
                n_total += 1
                old = prev.get(key)
                if not t.any():
                    if skip_black:
                        if old is BLACK or old is None:
                            prev[key] = BLACK
                            continue
                        ops.append(("clear", ox + tx, oy + ty, tw, th, None))
                        prev[key] = BLACK
                        continue
                    payload = bytes((tw // 8) * th)
                    if mode == "delta" and old == payload:
                        continue
                    ops.append(("send", ox + tx, oy + ty, tw, th, payload))
                    prev[key] = payload
                    continue
                payload = np.packbits(t, axis=1).tobytes()
                if mode == "delta" and old == payload:
                    continue
                ops.append(("send", ox + tx, oy + ty, tw, th, payload))
                prev[key] = payload
    for key, old in list(prev.items()):
        if key not in current and old is not BLACK and old is not None:
            ops.append(("clear", key[0], key[1], tile, tile, None))
            prev[key] = BLACK
    return ops, n_total
