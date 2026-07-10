from evalops_dashboard.cost import calculate_cost


def test_calculates_cost_from_token_counts_and_prices() -> None:
    cost = calculate_cost(
        input_tokens=2000,
        output_tokens=1000,
        input_price_per_1k_tokens=0.005,
        output_price_per_1k_tokens=0.015,
    )

    assert cost == 0.025


def test_zero_tokens_costs_nothing() -> None:
    cost = calculate_cost(
        input_tokens=0,
        output_tokens=0,
        input_price_per_1k_tokens=0.01,
        output_price_per_1k_tokens=0.03,
    )

    assert cost == 0.0


def test_rounds_to_six_decimal_places() -> None:
    cost = calculate_cost(
        input_tokens=1,
        output_tokens=1,
        input_price_per_1k_tokens=0.0000001,
        output_price_per_1k_tokens=0.0000001,
    )

    assert cost == 0.0


def test_input_and_output_prices_are_calculated_independently() -> None:
    cost = calculate_cost(
        input_tokens=1000,
        output_tokens=0,
        input_price_per_1k_tokens=0.02,
        output_price_per_1k_tokens=100.0,
    )

    assert cost == 0.02
