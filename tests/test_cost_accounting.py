from backend.executors.provider_adapters import _calc_cost_usd, _to_int


def test_to_int_handles_none_and_bad_values():
    assert _to_int(None) == 0
    assert _to_int("") == 0
    assert _to_int("12") == 12
    assert _to_int("bad") == 0


def test_calc_cost_usd_openai_style_pricing():
    pricing = {"input_per_1k_usd": 0.005, "output_per_1k_usd": 0.015}
    # 1000 prompt + 2000 completion => 0.005 + 0.03 = 0.035
    assert _calc_cost_usd(1000, 2000, pricing) == 0.035


def test_calc_cost_usd_anthropic_style_pricing():
    pricing = {"input_per_1k_usd": 0.003, "output_per_1k_usd": 0.015}
    # 500 prompt + 500 completion => 0.0015 + 0.0075 = 0.009
    assert _calc_cost_usd(500, 500, pricing) == 0.009


def test_calc_cost_rounding_stable():
    pricing = {"input_per_1k_usd": 0.005, "output_per_1k_usd": 0.015}
    value = _calc_cost_usd(1234, 5678, pricing)
    assert isinstance(value, float)
    # Check exact rounded value to 6 decimals.
    assert value == round(value, 6)
