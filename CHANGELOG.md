Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

5.2.0 - 2026-03-30

Added

Initial public release of the core mesh architecture.

Ed25519 packet signatures for robust message authentication.

X25519 key agreement established per peer for secure communication.

ChaCha20Poly1305 encryption (AEAD) for high-performance confidentiality.

Replay protection utilizing a sliding timestamp window and nonce cache.

Score-based leader election featuring epoch protection to prevent split-brain scenarios.

Real Wi-Fi RSSI monitoring via Termux:API integration for Android environments.

Health monitoring state machine (Suspect → Offline) for self-healing topology.

Live terminal dashboard for real-time tracking of throughput, latency, and node scores.

Graceful shutdown handling for clean socket cleanup via Ctrl+C.

Full test suite with >80% code coverage.

Security

Mandatory authentication: All packets must be signed with Ed25519.

Secret derivation: Per-peer secrets derived via X25519 ECDH + HKDF.

Hardened replay protection against network-level spoofing.

Known Limitations

Boundary Security: Designed primarily for trusted network boundaries (no mutual authentication in v5.2).

DoS: Basic rate limiting implemented; not yet hardened against high-velocity flooding.

PFS: Lack of Perfect Forward Secrecy; keys are persistent across sessions.

[6.0.0] - Planned

Planned Features

[ ] Mutual peer authentication for zero-trust environments.

[ ] Forward secrecy implementation using the Double Ratchet algorithm.

[ ] Per-session key rotation to minimize compromise windows.

[ ] Known-peers whitelist for restricted network access.

[ ] DoS hardening utilizing token bucket algorithms.

[ ] Private/targeted messaging directed by specific Node ID.

[ ] Bluetooth transport support via bleak and RFCOMM.

Peer Note: This looks great for the 2026 market. By dating it today, you're effectively putting a stake in the ground for the official launch. Since you're targeting that 2-week roadmap, having the v6.0.0 "Planned" section visible is a great way to signal to potential contributors that the project has a long-term vision.

