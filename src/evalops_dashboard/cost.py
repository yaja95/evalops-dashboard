def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_1k_tokens: float,
    output_price_per_1k_tokens: float,
) -> float:
    cost = (input_tokens / 1000) * input_price_per_1k_tokens + (
        output_tokens / 1000
    ) * output_price_per_1k_tokens
    return round(cost, 6)
