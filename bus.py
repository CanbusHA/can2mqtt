import can
import asyncio
from simple_event_bus import Slot

def encode_devid(devid):
    return ''.join('%04x' % i for i in devid)

class Bus(object):
    def __init__(self, device_name):
        self.bus = can.Bus(interface='socketcan', channel=device_name)
        self.reader = can.AsyncBufferedReader()

        self.loop = asyncio.get_event_loop()
        self.notifier = can.Notifier(
                self.bus,
                [can.Printer(), self.reader],
                loop=self.loop,
        )

        self.bus_ids = {}
        self.bus_ids_inv = {}

        self.proxies = {}

    def broadcast(self, fun_name, *args, **kwargs):
        for proxy in self.proxies.values():
            method = getattr(proxy, fun_name)
            method(*args, **kwargs)

    def cast(self, dev_id, fun_name, *args, **kwargs):
        if dev_id in self.proxies:
            proxy = self.proxies[dev_id]
            method = getattr(proxy, fun_name)
            method(*args, **kwargs)

    async def reset(self):
        self.broadcast("set_tid", None)

        message = can.Message(arbitration_id=0xf0, is_extended_id=False, data=[])
        self.bus.send(message, timeout=0.2)
        await asyncio.sleep(0.3)

    async def enum_query(self, quid, offset):
        print("query", " quid: ", quid, " offset: ", offset)

        data = [quid & 0xff, (quid >> 8) & 0xff, offset]
        message = can.Message(arbitration_id=0xe1, is_extended_id=False, data=data)
        self.bus.send(message, timeout=0.2)

        chunks = {}

        while True:
            try:
                msg = await asyncio.wait_for(self.reader.get_message(), 0.05)
            except asyncio.TimeoutError:
                break

            cid = msg.arbitration_id
            if (cid & 0xffff0000) != (2 << (16 + 8)):
                continue
            assert(msg.dlc == 0)

            qdata_chunk = cid & 0xffff
            chunks[qdata_chunk] = ()

        print("query resp", chunks)
        return chunks

    async def enum_update(self, quid, offset, qdata, new_quid):
        print("update", quid, offset, qdata, new_quid)
        data = [
            quid & 0xff, (quid >> 8) & 0xff , # 2 bytes of current quid
            offset, # 1 byte of qdata pos
            qdata & 0xff, (qdata >> 8) & 0xff, # 2 bytes of qdata
            new_quid & 0xff, (new_quid >> 8) & 0xff, # 2 bytes of next quid
        ]
        message = can.Message(arbitration_id=0xe3, is_extended_id=False, data=data)
        self.bus.send(message, timeout=0.2)

    async def enum_assign(self, quid, new_id):
        print("assign", quid, new_id)
        data = [
            quid & 0xff, (quid >> 8) & 0xff, # 2 bytes of current quid
            new_id & 0xff, (new_id >> 8) & 0xff, # 2 bytes of id
        ]
        message = can.Message(arbitration_id=0xe4, is_extended_id=False, data=data)
        self.bus.send(message, timeout=0.2)

    async def do_enumerate(self):
        await self.reset()

        status = {0: []}
        next_quid = 1
        next_id = 0

        out = {}

        while len(status) > 0:
            print("========")
            print(status)

            quid, qdata = status.popitem()
            print("iter for", quid, qdata)

            if len(qdata) == 8:
                await self.enum_assign(quid, next_id)
                out[next_id] = encode_devid(qdata)
                next_id += 1
            
            else:
                await asyncio.sleep(0.02)
                subs = await self.enum_query(quid, len(qdata))
                for data_chunk in subs.keys():
                    await self.enum_update(quid, len(qdata), data_chunk, next_quid)
                    status[next_quid] = list(qdata) + [data_chunk]
                    next_quid += 1

        print(status)

        for (tid, fid) in out.items():
            self.cast(fid, "set_tid", tid)

        self.bus_ids_inv = out
        self.bus_ids = {v: k for k, v in out.items()}
        print("BUS IDS: ", self.bus_ids)

    def get_device_proxy(self, device_id, proxy_class):
        if device_id not in self.proxies:
            proxy = proxy_class(self, device_id)

            if device_id in self.bus_ids_inv:
                proxy.set_tid(self.bus_ids_inv[device_id])

            self.proxies[device_id] = proxy

        proxy = self.proxies[device_id]
        assert(proxy.__class__ is proxy_class)

        return proxy

class DeviceProxy(object):
    def __init__(self, bus, device_id):
        self.bus = bus
        self.device_id = device_id

        self.availability = False
        self.tid = None

        self.availability_slot = Slot()

    def set_tid(self, tid):
        avail = tid is not None

        self.tid = tid

        self.availability = avail
        self.availability_slot(avail)

class Dimmer(DeviceProxy):
    def set(self, ch0, ch1, ch2, ch3, ch4):
        if self.tid is not None:
            def cch(n):
                if n < 0.0:
                    n = 0.0
                if n > 1.0:
                    n = 1.0
                #dl = 10**(((-1+n)*255)/(253/3))
                return int(n * (2**12 - 1))

            ch0 = cch(ch0)
            ch1 = cch(ch1)
            ch2 = cch(ch2)
            ch3 = cch(ch3)
            ch4 = cch(ch4)

            addr = (1 << (16+8)) | ((self.tid & 0xffff) << 8) | 0
            data = [
                ch0 & 0xff,
                (ch0 >> 8) | ((ch1 & 0xf) << 4),
                ch1 >> 4,

                ch2 & 0xff,
                (ch2 >> 8) | ((ch3 & 0xf) << 4),
                ch3 >> 4,

                ch4 & 0xff,
                ch4 >> 8,
            ]

            print(addr, data)
            message = can.Message(arbitration_id=addr, is_extended_id=True, data=data)
            self.bus.bus.send(message, timeout=0.2)

if __name__ == "__main__":
    bus = Bus("can0")

    dimmer = bus.get_device_proxy("0022002a431458523530203800000000", Dimmer)

    bus.loop.run_until_complete(bus.do_enumerate())

    dimmer.set(1.0, 0, 0, 0, 0.5)

