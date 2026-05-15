from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.config import settings

MONEY_QUANT = Decimal("0.01")
DEFAULT_PLATFORM_FEE_RATE = Decimal("0.001")
PLATFORM_FEE_FORMULA = "platform_fee = execution_price * quantity * platform_fee_rate"
PLATFORM_FEE_ROUNDING = "Round half up to 2 decimal places"

_platform_profit_total = Decimal("0.00")


def _to_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def money(value) -> Decimal:
    return _to_decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def get_platform_fee_rate() -> Decimal:
    rate = _to_decimal(settings.PLATFORM_FEE_RATE, DEFAULT_PLATFORM_FEE_RATE)
    if rate < 0:
        return DEFAULT_PLATFORM_FEE_RATE
    return rate


def calculate_trade_value(quantity, price) -> Decimal:
    quantity_dec = _to_decimal(quantity)
    price_dec = _to_decimal(price)
    if quantity_dec <= 0 or price_dec <= 0:
        return Decimal("0.00")
    return money(quantity_dec * price_dec)


def calculate_platform_fee(quantity, price, fee_rate: Decimal | None = None) -> Decimal:
    rate = get_platform_fee_rate() if fee_rate is None else fee_rate
    quantity_dec = _to_decimal(quantity)
    price_dec = _to_decimal(price)
    if quantity_dec <= 0 or price_dec <= 0 or rate <= 0:
        return Decimal("0.00")
    return money(quantity_dec * price_dec * rate)


def calculate_total_fee(exchange_fee, platform_fee) -> Decimal:
    return money(_to_decimal(exchange_fee) + _to_decimal(platform_fee))


def record_platform_profit(amount) -> Decimal:
    global _platform_profit_total
    collected = money(amount)
    if collected <= 0:
        return _platform_profit_total
    _platform_profit_total = money(_platform_profit_total + collected)
    return _platform_profit_total


def get_platform_profit_total() -> Decimal:
    return _platform_profit_total


def get_fee_policy() -> dict:
    return {
        "platform_fee_rate": float(get_platform_fee_rate()),
        "formula": PLATFORM_FEE_FORMULA,
        "rounding": PLATFORM_FEE_ROUNDING,
        "platform_profit_total": float(get_platform_profit_total()),
    }


def reset_platform_profit_total() -> None:
    global _platform_profit_total
    _platform_profit_total = Decimal("0.00")
