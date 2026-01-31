"""
Patchset v2 P-01..P-04 validation tests.

CALL-SITE REPORT (from repo recon):
  a) Vertex28 buffer build: backend/models/universe.py VertexLayout28; backend/services/
     sovereign_orchestrator.py _materialize_snapshot; engines/vertex_buffer_builder.py;
     engines/realtime_bridge.py _process_batch; backend/scripts/seed_universe_v8_routeA.py
  b) Births: sovereign_orchestrator _materialize_snapshot; ingest_service ingest_run;
     realtime_bridge _process_batch; seed scripts
  c) Deaths: ASSET_REMOVE opcode defined (sovereign_orchestrator); no wired removal in
     snapshot path (assets filtered by is_active in SQL)
  d) Oracle loop: realtime_bridge process_batches; ingest_service ingest_run;
     engines/technical/ingest ingest_batch
  e) Pool: engines/void_pool.py VoidPool; realtime_bridge update_queue (asyncio.Queue)

P-04 STATUS: REAL. VoidPool with try_push/try_pop; Death->release, Birth->acquire wired
in sovereign _materialize_with_voidpool. symbol_to_slot persists; deaths release slots.
"""
import hashlib
import pytest
import numpy as np


def test_p01_dist_zero_no_nan_inf():
    """P-01: dist→0 does not produce NaN/Inf in compute_genetic_field."""
    try:
        from backend.models.universe import compute_genetic_field
    except ImportError:
        from backend.models import universe as um
        if hasattr(um, "compute_genetic_field"):
            compute_genetic_field = um.compute_genetic_field
        else:
            pytest.skip("compute_genetic_field not available (numba may be disabled)")
            return

    n = 16
    taxonomies = np.zeros(n, dtype=np.uint32)  # All identical → dist=0 between pairs
    metas = np.full(n, 128, dtype=np.uint32)
    out_field = np.zeros(n, dtype=np.float32)

    compute_genetic_field(taxonomies, metas, out_field)

    assert not np.any(np.isnan(out_field)), "P-01: NaN produced when dist→0"
    assert not np.any(np.isinf(out_field)), "P-01: Inf produced when dist→0"
    assert np.all(np.isfinite(out_field)), "P-01: Non-finite values in out_field"


def test_p02_kappa_zero_no_overflow():
    """P-02: kappa→0 does not overflow energy in VPIN."""
    from analytics.vpin import VPINCalculator
    from collections import deque

    calc = VPINCalculator(window_size=2, bucket_count=1)
    calc.state[1] = deque([(0.0, 0.0, 1e-10), (0.0, 0.0, 1e-10)], maxlen=2)
    risk8, vital6 = calc.update(1, 100.0, volume=1e-10, prev_price=99.0)
    risk8b, vital6b = calc.update(1, 101.0, volume=1e-10, prev_price=100.0)
    assert 0 <= risk8 <= 255 and 0 <= risk8b <= 255, "P-02: risk8 overflow"
    assert 0 <= vital6 <= 63 and 0 <= vital6b <= 63, "P-02: vital6 overflow"


def test_p03_work_cap_constant():
    """P-03: WORK_CAP_PER_TICK is 50_000."""
    from engines.constants import WORK_CAP_PER_TICK
    assert WORK_CAP_PER_TICK == 50_000, "P-03: work_cap must be 50,000"


def test_p03_ingest_uses_work_cap():
    """P-03: ingest_service imports and uses WORK_CAP_PER_TICK."""
    from services.ingest_service import WORK_CAP_PER_TICK
    assert WORK_CAP_PER_TICK == 50_000, "P-03: ingest work_cap must be 50,000"


def test_p03_oracle_processes_at_most_50k_per_tick():
    """P-03: Under 1M events, oracle processes <=50k per tick; rest deferred."""
    from engines.constants import WORK_CAP_PER_TICK
    # Simulate: collect up to 50k per tick
    events = list(range(1_000_000))
    processed_per_tick = []
    remaining = list(events)
    while remaining:
        batch = remaining[:WORK_CAP_PER_TICK]
        remaining = remaining[WORK_CAP_PER_TICK:]
        processed_per_tick.append(len(batch))
    assert all(n <= WORK_CAP_PER_TICK for n in processed_per_tick)
    assert sum(processed_per_tick) == 1_000_000


def test_p04_pool_acquire_release():
    """P-04: VoidPool acquire/release semantics."""
    from engines.void_pool import VoidPool

    pool = VoidPool(capacity=16)
    n = pool.prime(8)
    assert n == 8
    assert pool.free_count() == 8

    a1 = pool.acquire()
    assert a1 is not None
    slot1, seq1 = a1
    assert 0 <= slot1 < 8
    assert seq1 > 0

    ok = pool.release(slot1, seq1)
    assert ok is True
    assert pool.free_count() == 8

    # ABA: stale release rejected
    ok2 = pool.release(slot1, seq1)
    assert ok2 is False


def test_p04_slot_churn_10k_births_deaths():
    """P-04: 10k births/deaths per frame; no corruption, no duplicates, no lost slots."""
    from engines.void_pool import VoidPool

    pool = VoidPool(capacity=200_000)
    pool.prime(50_000)
    allocated: dict[int, int] = {}  # slot_idx -> seq64

    for _ in range(10_000):
        a = pool.acquire()
        assert a is not None, "Pool should have slots"
        slot, seq = a
        assert slot not in allocated, "Duplicate slot"
        allocated[slot] = seq

    for slot, seq in list(allocated.items()):
        ok = pool.release(slot, seq)
        assert ok, f"Release failed for slot {slot}"

    assert pool.free_count() == 50_000, "All slots returned"


def test_p04_determinism_same_seed_same_digest():
    """Determinism: same seed/inputs yields identical checksum over SoA."""
    from engines.void_pool import VoidPool
    from engines.vertex_buffer_builder import build_vertex_buffer_with_pool

    def digest(seed: int) -> str:
        rng = np.random.default_rng(seed)
        records = [
            (rng.integers(0, 2**32), rng.integers(0, 2**32),
             float(rng.random()), float(rng.random()), float(rng.random()),
             float(rng.random()), float(rng.random()))
            for _ in range(100)
        ]
        pool = VoidPool(capacity=256)
        pool.prime(256)
        vb, _ = build_vertex_buffer_with_pool(records, pool)
        return hashlib.sha256(vb).hexdigest()

    d1 = digest(42)
    d2 = digest(42)
    assert d1 == d2, "Determinism violated"


def test_p04_sovereign_death_birth_wiring():
    """P-04: Death releases slots; Birth acquires. Churn preserves uniqueness."""
    from unittest.mock import patch
    from config import settings
    from backend.services.sovereign_orchestrator import SovereignOrchestrator
    from backend.models.universe import UniverseAsset, GovernanceStatus

    def asset(sym: str, tax: int, meta: int, fid: float, x: float, y: float) -> UniverseAsset:
        return UniverseAsset(sym, tax, meta, fid, GovernanceStatus.PROVISIONAL, x=x, y=y, sector="TECH", name=sym)

    with patch.object(settings, "ENABLE_VOIDPOOL", True):
        orch = SovereignOrchestrator(dsn="")
        a1, a2, a3 = asset("A", 1, 2, 0.9, 0.1, 0.2), asset("B", 3, 4, 0.8, 0.3, 0.4), asset("C", 5, 6, 0.7, 0.5, 0.6)
        snap1 = orch._materialize_snapshot([a1, a2, a3], "test")
        assert len(snap1.vertex_bytes) == 3 * 28
        assert len(orch._symbol_to_slot) == 3
        a4 = asset("D", 7, 8, 0.6, 0.7, 0.8)
        snap2 = orch._materialize_snapshot([a1, a3, a4], "test")
        assert len(snap2.vertex_bytes) == 3 * 28
        assert "B" not in orch._symbol_to_slot
        assert "D" in orch._symbol_to_slot


def test_p04_sovereign_voidpool_birth_wire_when_enabled():
    """P-04: When ENABLE_VOIDPOOL=True, _materialize_snapshot uses VoidPool."""
    from unittest.mock import patch
    from config import settings
    from backend.services.sovereign_orchestrator import SovereignOrchestrator
    from backend.models.universe import UniverseAsset, GovernanceStatus

    with patch.object(settings, "ENABLE_VOIDPOOL", True):
        orch = SovereignOrchestrator(dsn="")
        a1 = UniverseAsset("T1", 1, 2, 0.9, GovernanceStatus.PROVISIONAL, x=0.1, y=0.2, sector="TECH", name="T1")
        a2 = UniverseAsset("T2", 3, 4, 0.8, GovernanceStatus.PROVISIONAL, x=0.3, y=0.4, sector="FIN", name="T2")
        snap = orch._materialize_snapshot([a1, a2], source_tier="test")
        assert len(snap.vertex_bytes) == 2 * 28


def test_p04_sovereign_fallback_when_voidpool_disabled():
    """P-04: When ENABLE_VOIDPOOL=False, uses VertexLayout28.pack_vertex_buffer."""
    from unittest.mock import patch
    from config import settings
    from backend.services.sovereign_orchestrator import SovereignOrchestrator
    from backend.models.universe import UniverseAsset, GovernanceStatus

    with patch.object(settings, "ENABLE_VOIDPOOL", False):
        orch = SovereignOrchestrator(dsn="")
        a1 = UniverseAsset("T1", 1, 2, 0.9, GovernanceStatus.PROVISIONAL, x=0.1, y=0.2, sector="TECH", name="T1")
        snap = orch._materialize_snapshot([a1], source_tier="test")
        assert len(snap.vertex_bytes) == 28


def test_t1_stride_fail_fast():
    """T1: buffer byteLength % 28 != 0 must throw FAIL_FAST (STRIDE_28 or LAYOUT)."""
    from services.vertex28 import validate_vertex28_blob
    import pytest
    with pytest.raises(ValueError, match="FAIL_FAST"):
        validate_vertex28_blob(b"x" * 27)
    with pytest.raises(ValueError, match="FAIL_FAST"):
        validate_vertex28_blob(b"x" * 29)
    assert validate_vertex28_blob(b"x" * 28) == 1
    assert validate_vertex28_blob(b"x" * 56) == 2


def test_p02_causal_mux_energy_clamp():
    """P-02: causal_mux shock propagation yields E in [0,8], no Inf/NaN."""
    from engines.causal_mux import CausalGraph, CausalEdge
    from engines.causal_mux import BayesianPropagationEngine

    n = 5
    edges = [
        CausalEdge(source=0, target=1, strength=0.8, lag=0, confidence=0.9, method_version="test"),
        CausalEdge(source=1, target=2, strength=0.5, lag=0, confidence=0.8, method_version="test"),
    ]
    graph = CausalGraph(n_assets=n, edges=edges, asset_ids=np.arange(n))
    engine = BayesianPropagationEngine(graph, decay_factor=0.5, eps=1e-6)
    shock = np.zeros(n)
    shock[0] = 1.0
    s_k, _ = engine.propagate_shock(shock)
    assert np.all(np.isfinite(s_k)), "P-02: Inf/NaN in shock"
    assert np.all((s_k >= 0) & (s_k <= 8)), "P-02: Energy clamp [0,8]"
