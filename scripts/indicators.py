"""Causal daily MSTR indicators computed from split-adjusted session bars."""
import math
from collections import deque
from datetime import date


def calculate(rows):
    """Return one observation per bar, including null warm-up periods.

    ATR% is the mean absolute open-to-close percent move over ten sessions;
    it is not the conventional true range ATR. RSI uses Wilder's original seed:
    arithmetic mean gains and losses from the first 40 close-to-close changes,
    followed by Wilder smoothing. A flat run has RSI 50.

    Reject the whole input if any included session has missing, non-positive or
    non-finite open/close data. This prevents silently bridging an OHLC gap.
    The caller keeps the last valid dataset on failure.
    """
    if not rows:
        raise ValueError('No equity bars available for indicators')
    out, changes = [], deque(maxlen=10)
    prev_close = None
    gains, losses = [], []
    avg_gain = avg_loss = None
    prev_date = None
    for row in rows:
        day = row.get('date')
        try:
            date.fromisoformat(day)
        except (TypeError, ValueError):
            raise ValueError('Invalid indicator observation date') from None
        if prev_date is not None and day <= prev_date:
            raise ValueError('Duplicate or unordered indicator observation date')
        prev_date = day
        opening, close = row.get('open'), row.get('sharePrice')
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in (opening, close)):
            raise ValueError('Missing or invalid open/close on '+day)
        changes.append(abs(100.0 * (close - opening) / opening))
        atr = sum(changes) / 10 if len(changes) == 10 else None
        rsi = None
        if prev_close is not None:
            change = close - prev_close
            gain, loss = max(change, 0), max(-change, 0)
            if avg_gain is None:
                gains.append(gain); losses.append(loss)
                if len(gains) == 40:
                    avg_gain, avg_loss = sum(gains) / 40, sum(losses) / 40
            else:
                avg_gain = (39 * avg_gain + gain) / 40
                avg_loss = (39 * avg_loss + loss) / 40
            if avg_gain is not None:
                if avg_gain == 0 and avg_loss == 0:
                    rsi = 50.0
                elif avg_loss == 0:
                    rsi = 100.0
                else:
                    rsi = 100.0 * avg_gain / (avg_gain + avg_loss)
        out.append(dict(date=day, atrPct10=atr, rsi40=rsi))
        prev_close = close
    return out
