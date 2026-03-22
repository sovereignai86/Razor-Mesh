# RAZOR-MESH v5.2                                                                                    
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python&logoColor=white)](https://python.org)                                                                       [![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Status: Production Ready](https://img.shields.io/badge/Status-Production_Ready-brightgreen?style=flat-square)](https://github.com/sovreignai86/Razor-Mesh)
[![CI](https://github.com/sovreignai86/Razor-Mesh/actions/workflows/ci.yml/badge.svg)](https://github.com/sovreignai86/Razor-Mesh/actions)                                                                
Secure, self-organizing UDP mesh network with real-time terminal dashboard, leader election, real Wi-Fi RSSI (via Termux:API), persistent node identity, replay protection, and simple chat messaging.    
Built and fully tested on Android/Termux — multi-node discovery, health monitoring, and leader election work reliably.

## Features

### Cryptographic security
- Ed25519 signatures on every packet
- X25519 key agreement + HKDF-derived ChaCha20Poly1305 per-peer encryption
- Replay protection (nonce cache + timestamp window)
- Persistent node ID & cryptographic keys across restarts

### Mesh networking
- Automatic UDP broadcast discovery
- Score-based leader election with epoch protection
- Node health monitoring (suspect → offline)
- Real Wi-Fi RSSI via Termux:API (with fallback)

### User experience
- Live terminal dashboard (throughput, RSSI, latency, scores)
- Broadcast chat messaging between nodes
- Interactive mode for real-time typing

### Production touches
- Graceful shutdown (Ctrl+C cleans up sockets/tasks)
- Detailed logging
- Modern Python packaging (pyproject.toml)
- GitHub Actions CI (Ruff linting)

## Quick Start (Termux / Android)

1. Clone the repo:
   ```bash
   git clone https://github.com/sovreignai86/razor-mesh.git
   cd razor-mesh
Install dependencies & project:
pkg install python-cryptography -y
pip install -e .
Launch nodes (in separate Termux sessions):
razor-mesh --port 4445
razor-mesh --port 4446
razor-mesh --port 4447 --send "Hello mesh network!"
Nodes discover each other automatically. One becomes LEADER. Messages appear live in consoles.
Dashboard Examples
Multi-node discovery with real RSSI and leader election:
�
Leader view with peers:
�
Project structure overview:
�
Project Structure
razor-mesh/
├── src/
│   └── razor_mesh/
│       ├── __init__.py
│       ├── core.py               # UDP mesh, dashboard, core logic
│       └── protocol/
│           ├── razorlink.py      # Frame format, AES-GCM crypto
│           └── razorbluetoothtransport.py  # Async Bluetooth/stream transport
├── tests/
│   └── test_razorlink.py
├── razor_mesh.py                 # CLI launcher
├── pyproject.toml
├── requirements.txt
├── README.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── .github/workflows/ci.yml
└── assets/                       # Screenshots
Development Setup
# Re-install after changes
pip install -e . --force-reinstall

# Run tests
python -m pytest tests/

# Lint
ruff check src/
Security Notes
All packets are signed (Ed25519)
Replay protection (nonce + timestamp)
Per-peer key agreement (X25519 + HKDF)
Persistent keys stored securely on disk
Limitations for v5.2:
Designed for trusted networks
Basic rate limiting (expandable)
No forward secrecy or key rotation yet
Planned for v6.0: mutual authentication, known-peers whitelist, DoS hardening.
License
MIT License — see LICENSE
Built With
Python 3.10+
cryptography (Ed25519, X25519, ChaCha20Poly1305)
asyncio (UDP networking)
Termux:API (real RSSI on Android)
Next Steps / Roadmap
Targeted/private messages (by node ID)
Bluetooth transport demo (bleak/RFCOMM)
Rate limiting & DoS protection
Known-peers authentication
Publish to PyPI
Contributions welcome — see CONTRIBUTING.md
Made on Termux — March 2026
