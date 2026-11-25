"""Protocole filaire ActiveLook (BLE GATT).

Sources :
- UUIDs + trames de demo (clear, texte 0x37) : fil Arduino "Writing to a BLE
  Characteristic" (commandes issues de l'API officielle ActiveLook).
- Commandes img* (0x40-0x45) : brevet MicroOLED EP4090057 / US20240233588.

Format constate : les trames commencent par 0xFF et finissent par 0xAA.
Les commandes > MTU sont envoyees en plusieurs ecritures GATT, les lunettes
reassemblent via la trame FF...AA.

A VALIDER sur materiel : imgStream (candidat A ci-dessous) et la
signification des 5 octets de parametres du texte.
"""

import struct

# --- GATT (constate, fil Arduino) ---
AL_SVC = "0783B03E-8535-B5A0-7140-A304D2495CB7"
AL_RX = "0783B03E-8535-B5A0-7140-A304D2495CBA"  # central -> lunettes (write)
AL_TX = "0783B03E-8535-B5A0-7140-A304D2495CB8"  # lunettes -> central (notify)
AL_CTL = "0783B03E-8535-B5A0-7140-A304D2495CB9"
ADV_PREFIX = "A.LooK"

# --- Trames connues (replay a l'identique) ---
CLEAR = bytes([0xFF, 0x01, 0x00, 0x05, 0xAA])
HELLO_DEMO = bytes.fromhex("FF3700140098008000020F68656C6C6F203000AA")

CMD_TEXT = 0x37
CMD_IMG_STREAM = 0x44
# Params de la demo texte : X=20, Y=152 puis ces 5 octets (sens exact inconnu :
# probablement rotation/font/taille/couleur). On rejoue a l'identique.
TEXT_DEMO_PARAMS = bytes([0x00, 0x80, 0x00, 0x02, 0x0F])


def build_text(x: int, y: int, text: str, params: bytes = TEXT_DEMO_PARAMS) -> bytes:
    """Construit une commande texte 0x37 (ASCII, terminee par 00).

    Hypothese (a valider) : X et Y sur 2 octets big-endian, comme la demo
    (X=0x0014=20, Y=0x0098=152 tiennent dans un 304x256).
    """
    asc = text.encode("ascii", errors="replace")
    return (b"\xFF" + bytes([CMD_TEXT]) + struct.pack(">H", x) + struct.pack(">H", y)
            + params + asc + b"\x00\xAA")


def build_imgstream_frame(x: int, y: int, w: int, payload: bytes) -> bytes:
    """CANDIDAT A : corps brevet (size LE32 + width LE16 + x/y) + framing FF..AA.

    Hauteur deduite cote lunettes : h = SIZE * 8 / WIDTH (1bpp).
    """
    body = (bytes([CMD_IMG_STREAM]) + struct.pack("<I", len(payload))
            + struct.pack("<H", w) + struct.pack("<h", x) + struct.pack("<h", y))
    return b"\xFF" + body + payload + b"\xAA"


def build_imgstream(x: int, y: int, w: int, payload: bytes, mtu_payload: int = 244) -> list:
    """Decoupe une trame imgStream candidate en chunks BLE."""
    blob = build_imgstream_frame(x, y, w, payload)
    return [blob[i:i + mtu_payload] for i in range(0, len(blob), mtu_payload)]


def chunk_count(payload_len: int, mtu_payload: int = 244) -> int:
    """Nombre de chunks BLE necessaires (11o corps + 2o framing + payload)."""
    total = 13 + payload_len
    return (total + mtu_payload - 1) // mtu_payload


def chunk_frame(frame: bytes, mtu_payload: int = 244) -> list:
    """Decoupe une trame quelconque (clear, texte...) en chunks BLE."""
    return [frame[i:i + mtu_payload] for i in range(0, len(frame), mtu_payload)]
