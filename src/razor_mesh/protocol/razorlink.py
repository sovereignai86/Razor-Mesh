import struct
import os
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# =======================
# CONSTANTS
# =======================
MAGIC = b"RZ"
VERSION = 0x01

TYPE_HANDSHAKE      = 0x01
TYPE_KEY_EXCHANGE   = 0x02
TYPE_RAZOR_COMMAND  = 0x03
TYPE_RAZOR_RESPONSE = 0x04
TYPE_HEARTBEAT      = 0x05
TYPE_ERROR          = 0x06


@dataclass
class RazorFrame:
    frame_type: int
    seq: int
    payload: bytes = b""

    def __post_init__(self) -> None:
        if not (0 <= self.frame_type <= 0xFF):
            raise ValueError("frame_type must be 0–255")
        if not (0 <= self.seq <= 0xFFFF):
            raise ValueError("seq must be 0–65535")


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 0x0001 else crc >> 1
    return crc & 0xFFFF


def encode_frame(frame: RazorFrame) -> bytes:
    payload = frame.payload or b""
    length = len(payload)
    header = struct.pack(">2s B B H H", MAGIC, VERSION, frame.frame_type, frame.seq, length)
    crc_input = struct.pack(">B B H H", VERSION, frame.frame_type, frame.seq, length) + payload
    crc = crc16_modbus(crc_input)
    return header + payload + struct.pack(">H", crc)


def decode_frame(data: bytes) -> RazorFrame:
    if len(data) < 10:
        raise ValueError("Frame too short")
    magic, version, ftype, seq, length = struct.unpack(">2s B B H H", data[:8])
    if magic != MAGIC or version != VERSION:
        raise ValueError("Bad magic or version")
    expected = 10 + length
    if len(data) != expected:
        raise ValueError(f"Length mismatch: expected {expected}, got {len(data)}")
    payload = data[8:8 + length]
    crc_recv = struct.unpack(">H", data[8 + length:])[0]
    crc_input = struct.pack(">B B H H", version, ftype, seq, length) + payload
    if crc16_modbus(crc_input) != crc_recv:
        raise ValueError("CRC mismatch")
    return RazorFrame(frame_type=ftype, seq=seq, payload=payload)


class RazorCrypto:
    def __init__(self, key: bytes):
        if len(key) not in (16, 24, 32):
            raise ValueError("AES key must be 16/24/32 bytes")
        self._aesgcm = AESGCM(key)

    def encrypt_frame(self, frame: RazorFrame, aad: Optional[bytes] = None) -> bytes:
        plaintext = encode_frame(frame)
        nonce = os.urandom(12)
        return nonce + self._aesgcm.encrypt(nonce, plaintext, aad or b"")

    def decrypt_frame(self, blob: bytes, aad: Optional[bytes] = None) -> RazorFrame:
        if len(blob) < 28:
            raise ValueError("Encrypted frame too short")
        nonce = blob[:12]
        ciphertext = blob[12:]
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, aad or b"")
        return decode_frame(plaintext)


class RazorLinkSequencer:
    def __init__(self, start: int = 0):
        self._seq = start & 0xFFFF

    def next(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        return self._seq


# High-level helpers
def build_command_frame(seq: int, payload: bytes) -> RazorFrame:
    return RazorFrame(TYPE_RAZOR_COMMAND, seq, payload)

def build_response_frame(seq: int, payload: bytes) -> RazorFrame:
    return RazorFrame(TYPE_RAZOR_RESPONSE, seq, payload)

def build_heartbeat_frame(seq: int) -> RazorFrame:
    return RazorFrame(TYPE_HEARTBEAT, seq, b"")

def build_error_frame(seq: int, message: str) -> RazorFrame:
    return RazorFrame(TYPE_ERROR, seq, message.encode("utf-8"))


__version__ = "0.1.0"
__all__ = ["RazorFrame", "RazorCrypto", "RazorLinkSequencer", "encode_frame", "decode_frame",
           "build_command_frame", "build_response_frame", "build_heartbeat_frame", "build_error_frame",
           "TYPE_HANDSHAKE", "TYPE_KEY_EXCHANGE", "TYPE_RAZOR_COMMAND", "TYPE_RAZOR_RESPONSE",
           "TYPE_HEARTBEAT", "TYPE_ERROR"]
