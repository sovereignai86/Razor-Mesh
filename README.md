# RAZOR-MESH v5.2

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg?style=flat-square)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)
![Status: Production Ready](https://img.shields.io/badge/Status-Production_Ready-brightgreen?style=flat-square)
![CI](https://github.com/YOUR-USERNAME/razor-mesh/actions/workflows/ci.yml/badge.svg)

**Secure, self-organizing UDP mesh network** with real-time terminal dashboard, leader election, real Wi-Fi RSSI (via Termux:API), persistent node identity, replay protection, and simple chat messaging.

Built and fully tested on Android/Termux — multi-node discovery, health monitoring, and leader election work reliably.

## Features

- **Cryptographic security**
  - Ed25519 signatures on every packet
  - X25519 key agreement + HKDF-derived ChaCha20Poly1305 per-peer encryption
  - Replay protection (nonce cache + timestamp window)
  - Persistent node ID & cryptographic keys across restarts

- **Mesh networking**
  - Automatic UDP broadcast discovery
  - Score-based leader election with epoch protection
  - Node health monitoring (suspect → offline)
  - Real Wi-Fi RSSI via Termux:API (with fallback)

- **User experience**
  - Live terminal dashboard (throughput, RSSI, latency, scores)
  - Broadcast chat messaging between nodes
  - Interactive mode for real-time typing

- **Production touches**
  - Graceful shutdown (Ctrl+C cleans up sockets/tasks)
  - Detailed logging
  - Modern Python packaging (pyproject.toml)
  - GitHub Actions CI (Ruff linting)

## Quick Start (Termux / Android)

1. Clone the repo:
   ```bash
   git clone https://github.com/YOUR-USERNAME/razor-mesh.git
   cd razor-mesh  
