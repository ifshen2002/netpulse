from services.simulator import SYNTHETIC_NODES, generate, is_on


def test_generate_returns_all_fields():
    for node_id in SYNTHETIC_NODES:
        m = generate(node_id)
        assert m is not None
        assert set(m.keys()) == {  # noqa: E501
            "node_id", "timestamp", "cpu", "memory", "disk",
            "latency_ms", "packet_loss_pct", "status",
        }


def test_generate_values_in_bounds():
    for _ in range(50):
        for node_id in SYNTHETIC_NODES:
            m = generate(node_id)
            assert 0 <= m["cpu"] <= 100
            assert 0 <= m["memory"] <= 100
            assert 0 <= m["latency_ms"]
            assert 0 <= m["packet_loss_pct"] <= 100


def test_generate_produces_varying_values():
    samples = {nid: [] for nid in SYNTHETIC_NODES}
    for _ in range(20):
        for nid in SYNTHETIC_NODES:
            samples[nid].append(generate(nid)["cpu"])
    for nid in SYNTHETIC_NODES:
        assert len(set(samples[nid])) > 1, f"Expected varying cpu values for {nid}"


def test_generate_unknown_node_returns_none():
    assert generate("node-99") is None


def test_is_on_defaults_true():
    assert is_on("node-2") is True
    assert is_on("node-3") is True
