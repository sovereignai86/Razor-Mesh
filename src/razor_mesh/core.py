import argparse
import asyncio
import base64
import json
import logging
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("razor-mesh")

class UI:
    PRIMARY   = "\033[38;5;75m"
    SUCCESS   = "\033[38;5;78m"
    WARNING   = "\033[38;5;214m"
    CRITICAL  = "\033[38;5;196m"
    DIM       = "\033[38;5;242m"
    BOLD      = "\033[1m"
    RESET     = "\033[0m"

@dataclass
class TrafficStats:
    pkts_in: int = 0
    pkts_out: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    last_reset: float = field(default_factory=time.time)

@dataclass
class SecureNode:
    id: str
    ip: str
    port: int
    pub_key: x25519.X25519PublicKey
    sign_key: ed25519.Ed25519PublicKey
    last_seen: float
    uptime: float = 0.0
    rssi: float = -100.0
    latency: float = 0.0
    score: float = 0.0
    is_alive: bool = True
    is_suspect: bool = False
    shared_secret: bytes = field(default=None)
    symmetric_key: bytes = field(default=None)
    leader_epoch: int = 0
    sent_timestamps: Dict[int, float] = field(default_factory=dict)  # nonce → send time

class MeshHealer:
    VERSION = "5.2"

    def __init__(self, bind_port: int = 4445):
        self.start_time = time.time()
        self.nodes: Dict[str, SecureNode] = {}
        self.leader_id: Optional[str] = None
        self.leader_epoch = 0

        self.traffic = TrafficStats()
        self.pps_in = 0
        self.pps_out = 0

        self.running = True
        self.bind_port = bind_port
        self.heartbeat_interval = 5.0
        self.grace_period = 6.0
        self.broadcast_addr = ("255.255.255.255", bind_port)

        self.node_file = os.path.expanduser("\~/.razor-mesh-node.json")
        self._load_persistent_state()

        self.transport = None
        self.local_ip = self._get_local_ip()

        # Replay protection + timestamp window
        self.recent_nonces: Dict[str, Deque[int]] = defaultdict(lambda: deque(maxlen=256))

        logger.info(f"Node ready | ID: {self.node_id} | Port: {bind_port} | IP: {self.local_ip}")

    def _load_persistent_state(self):
        if os.path.exists(self.node_file):
            try:
                with open(self.node_file, "r") as f:
                    data = json.load(f)
                    self.node_id = data["node_id"]
                    sign_priv_bytes = base64.b64decode(data["sign_priv"])
                    x_priv_bytes = base64.b64decode(data["x_priv"])
                    self.sign_priv = ed25519.Ed25519PrivateKey.from_private_bytes(sign_priv_bytes)
                    self.x_priv = x25519.X25519PrivateKey.from_private_bytes(x_priv_bytes)
                    self.sign_pub = self.sign_priv.public_key()
                    self.x_pub = self.x_priv.public_key()
                    logger.info(f"Loaded persistent state: {self.node_id}")
                    return
            except Exception as e:
                logger.warning(f"Persistent state load failed: {e}")

        # Generate new
        self.node_id = str(uuid.uuid4())[:8]
        self.sign_priv = ed25519.Ed25519PrivateKey.generate()
        self.sign_pub = self.sign_priv.public_key()
        self.x_priv = x25519.X25519PrivateKey.generate()
        self.x_pub = self.x_priv.public_key()

        # Save
        try:
            data = {
                "node_id": self.node_id,
                "sign_priv": base64.b64encode(self.sign_priv.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption()
                )).decode(),
                "x_priv": base64.b64encode(self.x_priv.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption()
                )).decode(),
            }
            with open(self.node_file, "w") as f:
                json.dump(data, f)
            logger.info(f"New persistent state saved: {self.node_id}")
        except Exception as e:
            logger.warning(f"Persistent state save failed: {e}")

    def _get_local_ip(self) -> str:
        for host in ["8.8.8.8", "1.1.1.1"]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect((host, 53))
                ip = s.getsockname()[0]
                s.close()
                if ip and ip != "127.0.0.1":
                    return ip
            except:
                pass
        return "127.0.0.1"

    def get_telemetry(self) -> float:
        try:
            out = subprocess.check_output(["termux-wifi-connectioninfo"], text=True, timeout=4)
            data = json.loads(out.strip())
            rssi = data.get("rssi")
            if isinstance(rssi, (int, float)):
                return float(rssi)
        except:
            pass
        return -55.0 + ((time.time() % 10) - 5)

    def calculate_score(self, uptime: float, rssi: float, latency: float) -> float:
        u = (uptime ** 0.5) * 0.3
        s = ((rssi + 100) / 100) * 0.5
        l = (latency * 10) * 0.2
        return max(0.0, u + s - l)

    def draw_dashboard(self):
        print("\033[H\033[J", end="", flush=True)  # Non-blocking clear
        role = f"{UI.SUCCESS}LEADER{UI.RESET}" if self.leader_id == self.node_id else f"{UI.PRIMARY}FOLLOWER{UI.RESET}"
        print(f"{UI.BOLD}RAZOR-MESH v{self.VERSION} | ID: {UI.PRIMARY}{self.node_id}{UI.RESET} | {role} | Epoch: {self.leader_epoch}")
        print(f"{UI.DIM}Local IP: {self.local_ip} | Port: {self.bind_port} | Uptime: {time.time() - self.start_time:.1f}s{UI.RESET}\n")

        print(f"{UI.BOLD}THROUGHPUT{UI.RESET}")
        print(f"IN: {self.pps_in:>4} pkt/s | {self.traffic.bytes_in / 1024:>6.1f} KB")
        print(f"OUT: {self.pps_out:>4} pkt/s | {self.traffic.bytes_out / 1024:>6.1f} KB\n")

        print(f"{UI.BOLD}{'PEER ID':<10} {'STATUS':<12} {'RSSI':<8} {'LATENCY':<10} {'SCORE':<10} {'ADDRESS':<15}{UI.RESET}")
        print(f"{UI.DIM}{'-' * 75}{UI.RESET}")

        my_rssi = self.get_telemetry()
        my_score = self.calculate_score(time.time() - self.start_time, my_rssi, 0.0)
        print(f"{UI.SUCCESS}{'SELF':<10}{UI.RESET} {'ACTIVE':<12} {my_rssi:<8.1f} {'0.0ms':<10} {my_score:<10.2f} {self.local_ip:<15}")

        for nid, n in sorted(self.nodes.items(), key=lambda x: x[1].score, reverse=True):
            color = UI.SUCCESS if n.is_alive and not n.is_suspect else (UI.WARNING if n.is_suspect else UI.CRITICAL)
            status = "SUSPECT" if n.is_suspect else ("ACTIVE" if n.is_alive else "OFFLINE")
            lead = "★ " if nid == self.leader_id else "  "
            print(f"{lead}{nid:<8} {color}{status:<12}{UI.RESET} {n.rssi:<8.1f} {n.latency*1000:<8.2f}ms {n.score:<10.2f} {n.ip:<15}")
        print(f"{UI.DIM}{'-' * 75}{UI.RESET}")

    async def secure_transmit(self, data: dict, target: Optional[tuple] = None, peer_nid: Optional[str] = None):
        if not self.transport or self.transport.is_closing():
            logger.warning("Transmit skipped - transport not ready")
            return

        now = time.time()
        nonce = secrets.randbits(64)

        payload = {
            "node_id": self.node_id,
            "ts": now,
            "nonce": nonce,
            "uptime": now - self.start_time,
            "rssi": self.get_telemetry(),
            **data
        }

        # Store send time for latency
        if "msg_type" in data and data["msg_type"] in ("heartbeat", "chat"):
            self.sent_timestamps[nonce] = now

        # Add keys for discovery
        payload.setdefault("pub_key", base64.b64encode(self.x_pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode())
        payload.setdefault("sign_pub", base64.b64encode(self.sign_pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode())
        payload.setdefault("leader_epoch", self.leader_epoch)

        # Encrypt unicast
        if target and peer_nid and peer_nid in self.nodes and self.nodes[peer_nid].symmetric_key:
            node = self.nodes[peer_nid]
            enc_nonce = secrets.token_bytes(12)
            inner = json.dumps(payload).encode()
            cipher = ChaCha20Poly1305(node.symmetric_key)
            ct = cipher.encrypt(enc_nonce, inner, None)
            outer = {
                "node_id": self.node_id,
                "ts": now,
                "nonce": secrets.randbits(64),
                "encrypted": True,
                "enc_nonce": base64.b64encode(enc_nonce).decode(),
                "ciphertext": base64.b64encode(ct).decode(),
            }
        else:
            outer = payload

        # Sign
        raw = json.dumps(outer, sort_keys=True, separators=(',', ':')).encode()
        signature = self.sign_priv.sign(raw)
        outer["signature"] = base64.b64encode(signature).decode()

        packet = json.dumps(outer).encode()
        dest = target if target else self.broadcast_addr

        try:
            self.transport.sendto(packet, dest)
            self.traffic.pkts_out += 1
            self.traffic.bytes_out += len(packet)
            logger.debug(f"Sent {len(packet)} bytes to {dest}")
        except Exception as e:
            logger.error(f"Send failed to {dest}: {e}")

    def _handle_packet(self, data: bytes, addr: tuple):
        self.traffic.pkts_in += 1
        self.traffic.bytes_in += len(data)

        try:
            msg = json.loads(data.decode())
        except json.JSONDecodeError:
            logger.debug(f"Invalid JSON from {addr}")
            return

        if "signature" not in msg or "sign_pub" not in msg:
            logger.debug(f"Missing signature from {addr} - dropped")
            return

        try:
            msg_no_sig = {k: v for k, v in msg.items() if k != "signature"}
            raw = json.dumps(msg_no_sig, sort_keys=True, separators=(',', ':')).encode()
            sign_key = ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(msg["sign_pub"]))
            sign_key.verify(base64.b64decode(msg["signature"]), raw)
        except Exception as e:
            logger.debug(f"Invalid signature from {addr}: {e} - dropped")
            return

        nid = msg.get("node_id")
        if not nid or nid == self.node_id:
            return

        # Replay protection + timestamp window
        nonce = msg.get("nonce")
        msg_ts = msg.get("ts", 0)
        age = time.time() - msg_ts
        if nonce is not None and msg_ts > 0:
            dq = self.recent_nonces[nid]
            if nonce in dq or age > 60 or age < -5:  # 60s window, 5s skew tolerance
                logger.debug(f"Replay/old packet from {nid} (age {age:.1f}s)")
                return
            dq.append(nonce)

        now = time.time()

        if nid not in self.nodes:
            try:
                peer_pub = x25519.X25519PublicKey.from_public_bytes(base64.b64decode(msg.get("pub_key", "")))
                node = SecureNode(id=nid, ip=addr[0], port=self.bind_port, pub_key=peer_pub, sign_key=sign_key, last_seen=now)
                node.shared_secret = self.x_priv.exchange(peer_pub)
                node.symmetric_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"razor-mesh-v1").derive(node.shared_secret)
                self.nodes[nid] = node
                logger.info(f"New peer: {nid} from {addr[0]}")
            except Exception as e:
                logger.warning(f"Key agreement failed for {nid}: {e}")
                return

        node = self.nodes[nid]
        node.leader_epoch = msg.get("leader_epoch", 0)

        # Latency: match nonce to stored send time
        if nonce in node.sent_timestamps:
            sent_time = node.sent_timestamps.pop(nonce)
            node.latency = max(0.0, now - sent_time)
        else:
            node.latency = max(0.0, now - msg.get("ts", now))

        if msg.get("encrypted"):
            if not node.symmetric_key:
                logger.debug(f"No key for {nid}")
                return
            try:
                enc_nonce = base64.b64decode(msg["enc_nonce"])
                ct = base64.b64decode(msg["ciphertext"])
                decrypted = ChaCha20Poly1305(node.symmetric_key).decrypt(enc_nonce, ct, None)
                inner = json.loads(decrypted.decode())
                msg.update(inner)
            except Exception as e:
                logger.debug(f"Decryption failed for {nid}: {e}")
                return

        node.last_seen = now
        node.is_alive = True
        node.is_suspect = False
        node.uptime = msg.get("uptime", 0.0)
        node.rssi = msg.get("rssi", -100.0)
        node.score = self.calculate_score(node.uptime, node.rssi, node.latency)

        if msg.get("is_leader"):
            self.leader_id = nid

        if msg.get("msg_type") == "chat":
            content = msg.get("content", "")
            if content:
                ts = time.strftime("%H:%M:%S", time.localtime(msg.get("ts", now)))
                print(f"{UI.WARNING}[CHAT {ts}] {nid} → {content}{UI.RESET}")

    def elect_leader(self):
        active = [n for n in self.nodes.values() if n.is_alive and not n.is_suspect]
        my_score = self.calculate_score(time.time() - self.start_time, self.get_telemetry(), 0.0)

        top = max(active, key=lambda x: (x.leader_epoch, x.score)) if active else None

        if not top or (self.leader_epoch, my_score) > (top.leader_epoch, top.score):
            if self.leader_id != self.node_id:
                self.leader_id = self.node_id
                self.leader_epoch += 1
                logger.info(f"Leader elected: {self.node_id} (epoch {self.leader_epoch})")
        else:
            self.leader_id = top.id

    async def monitor_task(self):
        while self.running:
            now = time.time()
            elapsed = now - self.traffic.last_reset
            if elapsed >= 1.0:
                self.pps_in = int(self.traffic.pkts_in / elapsed)
                self.pps_out = int(self.traffic.pkts_out / elapsed)
                self.traffic.pkts_in = self.traffic.pkts_out = 0
                self.traffic.last_reset = now

            self.draw_dashboard()

            for nid, n in list(self.nodes.items()):
                gap = now - n.last_seen
                if gap > self.heartbeat_interval and not n.is_suspect:
                    n.is_suspect = True
                if n.is_suspect and gap < self.grace_period:
                    await self.secure_transmit({"msg_type": "PROBE"}, target=(n.ip, n.port), peer_nid=nid)
                if gap > self.grace_period:
                    n.is_alive = n.is_suspect = False
                    self.elect_leader()

            await asyncio.sleep(0.5)

    async def heartbeat_task(self):
        while self.running:
            await self.secure_transmit({"is_leader": self.leader_id == self.node_id})
            await asyncio.sleep(self.heartbeat_interval)

    def _shutdown(self):
        self.running = False
        logger.info("Shutdown requested")

    async def run(self):
        loop = asyncio.get_running_loop()

        def shutdown():
            self._shutdown()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, shutdown)
            except NotImplementedError:
                pass

        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: self.SecureProtocol(self),
                local_addr=("0.0.0.0", self.bind_port),
                allow_broadcast=True,
                reuse_port=True,
            )
            logger.info("UDP transport bound")

            sock = transport.get_extra_info("socket")
            if sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            self.transport = transport

            tasks = [
                asyncio.create_task(self.heartbeat_task()),
                asyncio.create_task(self.monitor_task())
            ]

            await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            logger.info("Tasks cancelled (shutdown)")
        except Exception as e:
            logger.critical("Run loop error", exc_info=True)
        finally:
            if self.transport and not self.transport.is_closing():
                self.transport.close()
                await self.transport.wait_closed()
            logger.info("Mesh stopped")

    class SecureProtocol(asyncio.DatagramProtocol):
        def __init__(self, outer):
            self.outer = outer

        def connection_made(self, transport):
            self.outer.transport = transport

        def datagram_received(self, data, addr):
            self.outer._handle_packet(data, addr)

# =======================
# CLI
# =======================
def main():
    parser = argparse.ArgumentParser(description="RAZOR-MESH v5.2")
    parser.add_argument("--port", type=int, default=4445)
    parser.add_argument("--send", type=str)
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()

    logger.info(f"Starting RAZOR-MESH v{MeshHealer.VERSION} on port {args.port}")

    healer = MeshHealer(bind_port=args.port)

    async def main_loop():
        mesh_task = asyncio.create_task(healer.run(), name="mesh-core")

        if args.send:
            await asyncio.sleep(1.0)  # give time for transport
            await healer.secure_transmit({"msg_type": "chat", "content": args.send})
            logger.info(f"Startup message sent: {args.send}")

        if args.interactive:
            print(f"{UI.BOLD}Chat mode: type messages and press Enter (Ctrl+C to exit){UI.RESET}")
            try:
                while healer.running:
                    text = await asyncio.to_thread(input, f"{UI.PRIMARY}> {UI.RESET}")
                    if text.strip():
                        await healer.secure_transmit({"msg_type": "chat", "content": text.strip()})
            except EOFError:
                pass
        else:
            await mesh_task

    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Graceful exit (Ctrl+C)")
    except Exception as e:
        logger.critical("Fatal error", exc_info=True)

if __name__ == "__main__":
    main()
