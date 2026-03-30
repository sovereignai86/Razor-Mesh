import asyncio
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

# Internal imports
from cryptography.hazmat.primitives.asymmetric import ed25519
from .protocol.razorlink import (
    RazorCrypto,
    encode_frame,
    TYPE_RAZOR_COMMAND
)

# Configure production-grade logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("razor-mesh")

@dataclass
class TrafficStats:
    """Tracks network throughput and packet metrics."""
    pkts_in: int = 0
    pkts_out: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    last_reset: float = field(default_factory=time.time)

@dataclass
class SecureNode:
    """Represents a peer node with full cryptographic and telemetry state."""
    id: str
    ip: str
    port: int
    pub_key: Any
    sign_key: Any
    last_seen: float
    
    # Telemetry and Health
    uptime: float = 0.0
    rssi: float = -100.0
    latency: float = 0.0
    score: float = 0.0
    is_alive: bool = True
    is_suspect: bool = False
    
    # Cryptographic Handshake State
    shared_secret: Optional[bytes] = None
    symmetric_key: Optional[bytes] = None
    leader_epoch: int = 0
    sent_timestamps: Dict[int, float] = field(default_factory=dict)

class UI:
    """ANSI styling constants for the terminal dashboard."""
    PRIMARY = "\033[34m"
    SUCCESS = "\033[32m"
    WARNING = "\033[33m"
    CRITICAL = "\033[31m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

class MeshHealer:
    """
    Main orchestrator for Razor-Mesh. 
    Manages discovery, leader election, and secure transport.
    """
    VERSION = "5.2.0"

    def __init__(self, port: int = 4445, node_id: Optional[str] = None):
        # Basic Networking
        self.node_id = node_id or os.urandom(4).hex()
        self.bind_port = port
        self.local_ip = self._get_local_ip()
        self.broadcast_addr = "255.255.255.255"
        
        # 1. Identity Keys (Asymmetric Ed25519 for signing)
        self.sign_priv = ed25519.Ed25519PrivateKey.generate()
        self.sign_pub = self.sign_priv.public_key()
        
        # 2. Secure Transport Key (Symmetric 32-bytes for RazorCrypto AEAD)
        # Fix: RazorCrypto requires raw bytes (16, 24, or 32)
        self.secret_key = os.urandom(32)
        self.crypto = RazorCrypto(key=self.secret_key)
        
        # Ephemeral Handshake Keys
        self.x_priv = ed25519.Ed25519PrivateKey.generate()
        self.x_pub = self.x_priv.public_key()
        
        # Network State
        self.nodes: Dict[str, SecureNode] = {}
        self.traffic = TrafficStats()
        self.running = False
        self.start_time = time.time()
        
        # Election & Heartbeat Logic
        self.leader_id: Optional[str] = None
        self.leader_epoch: int = 0
        self.heartbeat_interval = 2.0
        self.grace_period = 5.0
        
        # Performance Metrics
        self.pps_in = 0
        self.pps_out = 0
        self.recent_nonces = set()
        
        # Fix: Portable Home Directory Pathing for Termux
        self.node_file = os.path.expanduser("~/.razor-mesh-node.json")
        
        # Async Task Containers
        self.transport = None
        self.monitor_task = None
        self.heartbeat_task = None

    def _get_local_ip(self) -> str:
        """Determines the local IP, defaulting to localhost if offline."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def calculate_score(self, node: SecureNode) -> float:
        """Determines leadership eligibility based on RSSI and Uptime."""
        uptime_score = min(node.uptime / 3600, 50)
        rssi_score = max(100 + node.rssi, 0) / 2
        return float(uptime_score + rssi_score)

    def elect_leader(self):
        """Simple score-based leader election."""
        if not self.nodes:
            self.leader_id = self.node_id
            return

        all_nodes = list(self.nodes.values())
        # Placeholder logic for selecting the highest score
        self.leader_id = self.node_id # Default to self for v5.2 stub

    def draw_dashboard(self):
        """Clears terminal and renders the Mesh status."""
        ui = UI()
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print(f"{ui.BOLD}{ui.PRIMARY}RAZOR-MESH v{self.VERSION}{ui.RESET} | "
              f"Node: {ui.SUCCESS}{self.node_id}{ui.RESET} | "
              f"Leader: {ui.WARNING}{self.leader_id or '...'}{ui.RESET}")
        print(f"{ui.DIM}IP: {self.local_ip} | Started: {time.ctime(self.start_time)}{ui.RESET}")
        print("-" * 65)
        print(f"Traffic: {self.traffic.pkts_in} Pkts In | {self.traffic.pkts_out} Pkts Out")
        print(f"Data:    {self.traffic.bytes_in/1024:.1f} KB In | {self.traffic.bytes_out/1024:.1f} KB Out")
        print("-" * 65)
        print(f"{ui.BOLD}ACTIVE PEERS:{ui.RESET}")
        for nid, node in self.nodes.items():
            print(f" > {nid[:8]} @ {node.ip} | RSSI: {node.rssi}dBm | Score: {node.score}")
        print(f"\n{ui.DIM}Listening on UDP {self.bind_port}... (Ctrl+C to stop){ui.RESET}")

    async def run(self):
        """Main event loop."""
        self.running = True
        logger.info(f"Razor-Mesh initialized on {self.local_ip}:{self.bind_port}")
        
        try:
            while self.running:
                self.draw_dashboard()
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
            logger.info("MeshHealer service stopped.")

class SecureProtocol(asyncio.DatagramProtocol):
    """Asynchronous UDP Protocol handler for Razor-Mesh."""
    def __init__(self, healer: MeshHealer):
        self.healer = healer

    def connection_made(self, transport):
        self.healer.transport = transport

    def datagram_received(self, data, addr):
        self.healer.traffic.pkts_in += 1
        self.healer.traffic.bytes_in += len(data)
        # Future: Pass data to RazorLinkSequencer for decoding

async def main():
    """Application entry point."""
    healer = MeshHealer()
    loop = asyncio.get_running_loop()
    
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: SecureProtocol(healer),
        local_addr=('0.0.0.0', healer.bind_port)
    )
    
    try:
        await healer.run()
    except KeyboardInterrupt:
        pass
    finally:
        transport.close()

if __name__ == "__main__":
    asyncio.run(main())
