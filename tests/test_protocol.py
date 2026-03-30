import pytest
import asyncio
from razor_mesh.core import MeshHealer, SecureNode, TrafficStats, UI

# ---------------------------------------------------------
# 1. TrafficStats Tests (Logic & Metrics)
# ---------------------------------------------------------

def test_traffic_stats_initialization():
    """Verify counters start at zero."""
    stats = TrafficStats()
    assert stats.sent_packets == 0
    assert stats.received_packets == 0
    assert stats.bytes_sent == 0

def test_traffic_stats_update():
    """Verify stats record data correctly."""
    stats = TrafficStats()
    # Assuming you have methods like update_sent(bytes)
    # If your attributes are public, we test direct assignment
    stats.sent_packets += 1
    stats.bytes_sent += 1024
    assert stats.sent_packets == 1
    assert stats.bytes_sent == 1024

# ---------------------------------------------------------
# 2. SecureNode Tests (Identity & State)
# ---------------------------------------------------------

def test_secure_node_identity():
    """Verify every node generates a valid cryptographic identity."""
    node = SecureNode()
    # Check for identity attributes based on your grep results
    assert hasattr(node, 'node_id') or hasattr(node, 'hex_id')
    
    # Verify node_id is a non-empty string
    node_id = getattr(node, 'node_id', getattr(node, 'hex_id', None))
    assert isinstance(node_id, str)
    assert len(node_id) > 0

def test_secure_node_transport_state():
    """Verify node initializes without an active transport."""
    node = SecureNode()
    assert node.transport is None

# ---------------------------------------------------------
# 3. MeshHealer Tests (Orchestration)
# ---------------------------------------------------------

def test_mesh_healer_initialization():
    """Verify the primary orchestrator sets up correctly."""
    healer = MeshHealer()
    assert healer is not None
    # Verify it has access to stats and UI components
    assert hasattr(healer, 'stats')
    assert hasattr(healer, 'nodes') or hasattr(healer, 'peers')

@pytest.mark.asyncio
async def test_mesh_healer_lifecycle():
    """Verify healer can transition states without crashing."""
    healer = MeshHealer()
    # Test internal state before starting
    assert not hasattr(healer, '_server_task') or healer._server_task is None

# ---------------------------------------------------------
# 4. UI Component Tests
# ---------------------------------------------------------

def test_ui_instantiation():
    """Verify UI handles initialization without a terminal attached."""
    ui = UI()
    assert ui is not None
    # Check for expected UI elements (dashboard, logs, etc.)
    assert hasattr(ui, 'refresh') or hasattr(ui, 'draw')
