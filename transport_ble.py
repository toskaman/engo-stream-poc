"""Transport BLE reel vers les lunettes (phase 2, apres validation emulee).

Usage :
  1. python stream.py --transport ble --ble-discover
     -> liste les lunettes visibles et leurs services/caracteristiques.
  2. Identifier la caracteristique de commande (ecriture) avec nRF Connect
     si besoin, valider le format imgStream (cf. protocol.py).
  3. python stream.py --transport ble --ble-address <MAC> --ble-write-uuid <UUID> ...

Necessite : pip install bleak
"""

import asyncio

from bleak import BleakClient, BleakScanner

from protocol import AL_RX, AL_TX, ADV_PREFIX, build_imgstream, chunk_frame


async def discover(timeout=8.0):
    print(f"Scan BLE ({timeout}s)...")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        mark = "  <-- LUNETTES ?" if (d.name or "").startswith(ADV_PREFIX) else ""
        print(f"  {d.address}  {d.name}  RSSI={d.rssi}{mark}")
    return devices


async def dump_services(address):
    async with BleakClient(address) as client:
        print(f"Connecte a {address}. Services :")
        for svc in client.services:
            print(f"  Service {svc.uuid}  {svc.description}")
            for ch in svc.characteristics:
                print(f"    Char {ch.uuid}  props={','.join(ch.properties)}  {ch.description}")


class BleGlasses:
    def __init__(self, address, write_uuid=None, notify_uuid=None,
                 mtu_payload=244, pace_ms=5.0):
        self.address = address
        self.write_uuid = write_uuid or AL_RX
        self.notify_uuid = notify_uuid or AL_TX
        self.mtu_payload = mtu_payload
        self.pace_s = pace_ms / 1000.0
        self.client = None
        self.tiles = 0
        self.bytes = 0
        self.frames = 0
        self.rx_log = []

    async def connect(self, subscribe=True):
        self.client = BleakClient(self.address)
        await self.client.connect()
        try:
            mtu = self.client.mtu_size  # negocié par l'OS (WinRT: lecture seule)
            self.mtu_payload = max(20, mtu - 3)
            print(f"Connecte a {self.address} (MTU={mtu}, RX={self.write_uuid})")
        except Exception:
            print(f"Connecte a {self.address} (MTU inconnu, chunks de {self.mtu_payload}o)")
        if subscribe:
            try:
                await self.client.start_notify(self.notify_uuid, self._on_notify)
                print(f"Notifications actives sur {self.notify_uuid}")
            except Exception as e:
                print(f"Notifications impossibles sur {self.notify_uuid} : {e}")

    def _on_notify(self, _handle, data: bytearray):
        self.rx_log.append(bytes(data))
        print(f"  [TX lunettes] {bytes(data).hex(' ')}")

    async def write_frame(self, frame: bytes):
        for chunk in chunk_frame(frame, self.mtu_payload):
            await self.client.write_gatt_char(self.write_uuid, chunk, response=False)
            self.bytes += len(chunk)
            if self.pace_s > 0:
                await asyncio.sleep(self.pace_s)
        self.frames += 1

    async def send_tile(self, x, y, w, h, payload: bytes):
        for chunk in build_imgstream(x, y, w, payload, self.mtu_payload):
            await self.client.write_gatt_char(self.write_uuid, chunk, response=False)
            self.bytes += len(chunk)
            if self.pace_s > 0:
                await asyncio.sleep(self.pace_s)
        self.tiles += 1

    async def clear_tile(self, x, y, w, h):
        # Repli honnete : pas de fillRect natif confirme -> on envoie une tuile noire.
        # Si le firmware expose un rectangle plein natif, le brancher ici (1 commande).
        await self.send_tile(x, y, w, h, bytes((w // 8) * h))

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            print("Deconnecte.")
