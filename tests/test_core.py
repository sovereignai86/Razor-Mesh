import pytest
import time
from cryptography.hazmat.primitives.asymmetric import ed25519
from razor_mesh.core import MeshHealer, SecureNode, TrafficStats, UI

@pytest.fixture
def mock_node_data():
    signing_key = ed25519.Ed25519PrivateKey.generate()
    return {
        "id": "test-node-01",
        "ip": "127.0.0.1",
        "port": 4445,
        "pub_key": signing_key.public_key(),
        "sign_key": signing_key,
        "last_seen": time.time()
    }

def test_traffic_stats_counters():
    stats = TrafficStats()
    stats.pkts_out += 1
    assert stats.pkts_out == 1

def test_node_initialization(mock_node_data):
    node = SecureNode(**mock_node_data)
    assert node.id == "test-node-01"
    assert node.is_alive is True

def test_mesh_healer_orchestration():
    """Verify MeshHealer initializes with required crypto keys."""
    # This now works because core.py handles the 'key' argument internally
    healer = MeshHealer()
    assert healer is not None
    assert hasattr(healer, 'crypto')
    assert healer.node_id is not None
    assert isinstance(healer.traffic, TrafficStats)

def test_ui_styling_constants():
    ui = UI()
    assert hasattr(ui, 'RESET')
    assert isinstance(ui.SUCCESS, str)
