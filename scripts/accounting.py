"""Pure, dependency-free validation and calculation contract for MSTR mNAV.

The adapter performs no networking, credential access, scheduling, publishing,
or file writes.  Callers supply an issuer capital snapshot and a paired MSTR/BTC
price observation.  Unknown fields fail closed so schema drift cannot silently
change a published ratio.
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
from typing import Any


SCHEMA_VERSION = "mstr-mnav-refresh/1.0"
DEBT_ROUNDING_TOLERANCE_USD = 1_000_000.0
DEFAULT_STALE_AFTER_DAYS = 14

CAPITAL_REQUIRED = {
    "schemaVersion", "asOf", "publishedAt", "readAt", "basicShares",
    "btcHeld", "usdReserve", "usdTreasuryCash", "preferredNotionalUSD",
    "options", "rsuPsu", "debtTranches", "strk",
}
CAPITAL_OPTIONAL = {"totalDebtUSD", "otherDebtUSD", "unmodeledSecurities", "sourceId"}
PRICE_REQUIRED = {
    "schemaVersion", "asOf", "publishedAt", "readAt", "stockPriceUSD",
    "btcPriceUSD",
}
PRICE_OPTIONAL = {"sourceId"}
DEBT_FIELDS = {"id", "principal", "conversionPrice", "conversionShares"}
STRK_FIELDS = {"id", "notionalUSD", "conversionPrice", "conversionShares"}


class ContractError(ValueError):
    """A validation error with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _reject_schema_keys(value: dict, required: set[str], optional: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise ContractError("invalid_type", f"{label} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing:
        raise ContractError("missing_required_data", f"{label} missing fields: {missing}")
    if unknown:
        raise ContractError("unknown_data", f"{label} has unknown fields: {unknown}")


def _number(value: Any, field: str, *, strictly_positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("invalid_type", f"{field} must be numeric")
    result = float(value)
    if strictly_positive and result <= 0:
        raise ContractError("nonpositive_value", f"{field} must be positive")
    if not strictly_positive and result < 0:
        raise ContractError("negative_value", f"{field} cannot be negative")
    if result != result or result in (float("inf"), float("-inf")):
        raise ContractError("nonfinite_value", f"{field} must be finite")
    return result


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str) or not value:
        raise ContractError("invalid_date", f"{field} must be a nonempty ISO date/time string")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ContractError("invalid_date", f"{field} is not ISO formatted: {value}") from exc


def _parse_instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ContractError("invalid_date", f"{field} must be a nonempty ISO date/time string")
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ContractError("invalid_date", f"{field} is not ISO formatted: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_capital_snapshot(snapshot: dict) -> dict:
    _reject_schema_keys(snapshot, CAPITAL_REQUIRED, CAPITAL_OPTIONAL, "capital snapshot")
    if snapshot["schemaVersion"] != SCHEMA_VERSION:
        raise ContractError("unsupported_schema", "capital snapshot schemaVersion is unsupported")
    as_of = _parse_date(snapshot["asOf"], "capital.asOf")
    published = _parse_instant(snapshot["publishedAt"], "capital.publishedAt")
    read_at = _parse_instant(snapshot["readAt"], "capital.readAt")
    if published.date() < as_of:
        raise ContractError("invalid_timeline", "capital publishedAt cannot precede capital asOf")
    if read_at < published:
        raise ContractError("invalid_timeline", "capital readAt cannot precede publishedAt")

    normalized = copy.deepcopy(snapshot)
    normalized["basicShares"] = _number(snapshot["basicShares"], "capital.basicShares", strictly_positive=True)
    normalized["btcHeld"] = _number(snapshot["btcHeld"], "capital.btcHeld", strictly_positive=True)
    for key in ("usdReserve", "usdTreasuryCash", "preferredNotionalUSD", "options", "rsuPsu"):
        normalized[key] = _number(snapshot[key], f"capital.{key}")

    if not isinstance(snapshot["debtTranches"], list):
        raise ContractError("invalid_type", "capital.debtTranches must be a list")
    debts, ids = [], set()
    for index, row in enumerate(snapshot["debtTranches"]):
        _reject_schema_keys(row, DEBT_FIELDS, set(), f"capital.debtTranches[{index}]")
        security_id = row["id"]
        if not isinstance(security_id, str) or not security_id:
            raise ContractError("invalid_id", f"capital.debtTranches[{index}].id must be nonempty")
        if security_id in ids:
            raise ContractError("duplicate_security", f"duplicate security id {security_id}")
        ids.add(security_id)
        debts.append({
            "id": security_id,
            "principal": _number(row["principal"], f"debt[{security_id}].principal"),
            "conversionPrice": _number(row["conversionPrice"], f"debt[{security_id}].conversionPrice", strictly_positive=True),
            "conversionShares": _number(row["conversionShares"], f"debt[{security_id}].conversionShares"),
        })
    normalized["debtTranches"] = debts

    _reject_schema_keys(snapshot["strk"], STRK_FIELDS, set(), "capital.strk")
    strk_id = snapshot["strk"]["id"]
    if not isinstance(strk_id, str) or not strk_id:
        raise ContractError("invalid_id", "capital.strk.id must be nonempty")
    if strk_id in ids:
        raise ContractError("duplicate_security", f"duplicate security id {strk_id}")
    normalized["strk"] = {
        "id": strk_id,
        "notionalUSD": _number(snapshot["strk"]["notionalUSD"], "capital.strk.notionalUSD"),
        "conversionPrice": _number(snapshot["strk"]["conversionPrice"], "capital.strk.conversionPrice", strictly_positive=True),
        "conversionShares": _number(snapshot["strk"]["conversionShares"], "capital.strk.conversionShares"),
    }
    if normalized["strk"]["notionalUSD"] > normalized["preferredNotionalUSD"]:
        raise ContractError("claim_mismatch", "STRK notional cannot exceed total preferred notional")

    tranche_total = sum(row["principal"] for row in debts)
    if "totalDebtUSD" in snapshot:
        issuer_total = _number(snapshot["totalDebtUSD"], "capital.totalDebtUSD")
        residual = issuer_total - tranche_total
        if abs(residual) > DEBT_ROUNDING_TOLERANCE_USD:
            raise ContractError(
                "unmodeled_debt",
                f"issuer totalDebtUSD differs from modeled tranches by {residual:,.2f}, above tolerance",
            )
        normalized["totalDebtUSD"] = issuer_total
    else:
        issuer_total, residual = tranche_total, 0.0
    normalized["_trancheDebtUSD"] = tranche_total
    normalized["_debtRoundingResidualUSD"] = residual
    normalized["_modeledTotalDebtUSD"] = issuer_total
    if "otherDebtUSD" in snapshot:
        normalized["otherDebtUSD"] = _number(snapshot["otherDebtUSD"], "capital.otherDebtUSD")
        normalized["_otherDebtScope"] = "caller_supplied_other_indebtedness"
    else:
        normalized["_otherDebtScope"] = "omitted_by_caller_defaulted_to_zero"
    normalized["_otherDebtUSD"] = normalized.get("otherDebtUSD", 0.0)

    unmodeled = snapshot.get("unmodeledSecurities", [])
    if not isinstance(unmodeled, list) or any(not isinstance(x, str) or not x for x in unmodeled):
        raise ContractError("invalid_type", "capital.unmodeledSecurities must be a list of nonempty strings")
    normalized["unmodeledSecurities"] = list(unmodeled)
    return normalized


def validate_price_observation(observation: dict) -> dict:
    _reject_schema_keys(observation, PRICE_REQUIRED, PRICE_OPTIONAL, "price observation")
    if observation["schemaVersion"] != SCHEMA_VERSION:
        raise ContractError("unsupported_schema", "price observation schemaVersion is unsupported")
    as_of = _parse_date(observation["asOf"], "price.asOf")
    published = _parse_instant(observation["publishedAt"], "price.publishedAt")
    read_at = _parse_instant(observation["readAt"], "price.readAt")
    if published.date() < as_of:
        raise ContractError("invalid_timeline", "price publishedAt cannot precede price asOf")
    if read_at < published:
        raise ContractError("invalid_timeline", "price readAt cannot precede publishedAt")
    normalized = copy.deepcopy(observation)
    normalized["stockPriceUSD"] = _number(observation["stockPriceUSD"], "price.stockPriceUSD", strictly_positive=True)
    normalized["btcPriceUSD"] = _number(observation["btcPriceUSD"], "price.btcPriceUSD", strictly_positive=True)
    return normalized


def select_capital_snapshot(snapshots: list[dict], observation_as_of: str) -> dict:
    """Select the latest snapshot known by a historical observation date.

    Both economic asOf and disclosure publishedAt must be on or before the
    observation date, preventing future capital lookahead in historical rows.
    """
    observation_date = _parse_date(observation_as_of, "observation.asOf")
    eligible = []
    for raw in snapshots:
        snapshot = validate_capital_snapshot(raw)
        as_of = _parse_date(snapshot["asOf"], "capital.asOf")
        published = _parse_instant(snapshot["publishedAt"], "capital.publishedAt").date()
        if as_of <= observation_date and published <= observation_date:
            eligible.append(snapshot)
    if not eligible:
        raise ContractError("future_capital_lookahead", "no capital snapshot was public by the observation date")
    eligible.sort(key=lambda x: (
        _parse_date(x["asOf"], "capital.asOf"),
        _parse_instant(x["publishedAt"], "capital.publishedAt"),
        _parse_instant(x["readAt"], "capital.readAt"),
    ))
    # Return the public contract shape.  Validation adds private reconciliation
    # fields for internal calculation, but calculate_for_observation deliberately
    # revalidates the selected snapshot at its public boundary.
    return {key: value for key, value in eligible[-1].items() if not key.startswith("_")}


def calculate_refresh(capital_snapshot: dict, price_observation: dict,
                      *, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
                      knowledge_basis: str = 'public_at_observation') -> dict:
    capital = validate_capital_snapshot(capital_snapshot)
    price = validate_price_observation(price_observation)
    capital_as_of = _parse_date(capital["asOf"], "capital.asOf")
    capital_published = _parse_instant(capital["publishedAt"], "capital.publishedAt").date()
    price_as_of = _parse_date(price["asOf"], "price.asOf")
    if knowledge_basis not in ('public_at_observation','retrospective_as_of_reconstruction'):
        raise ContractError('invalid_knowledge_basis','Explicit supported knowledge basis required')
    if capital_as_of > price_as_of or (capital_published > price_as_of and knowledge_basis=='public_at_observation'):
        raise ContractError("future_capital_lookahead", "capital snapshot was not public by the paired price date")
    if not isinstance(stale_after_days, int) or stale_after_days < 0:
        raise ContractError("invalid_threshold", "stale_after_days must be a nonnegative integer")

    age_days = (price_as_of - capital_as_of).days
    flags = []
    if knowledge_basis=='retrospective_as_of_reconstruction':
        flags.append('retrospective_reconstruction_not_point_in_time')
    if age_days > stale_after_days:
        flags.append("stale_capital_snapshot")
    if capital["unmodeledSecurities"]:
        flags.append("unmodeled_security")

    freshness_status = "stale_carried_forward" if age_days > stale_after_days else (
        "same_day_issuer_snapshot" if age_days == 0 else "carried_forward_issuer_snapshot")
    observation = {
        "schemaVersion": SCHEMA_VERSION,
        "asOf": price["asOf"],
        "publishedAt": price["publishedAt"],
        "readAt": price["readAt"],
        "capitalAsOf": capital["asOf"],
        "capitalPublishedAt": capital["publishedAt"],
        "capitalReadAt": capital["readAt"],
    }
    reconciliation = {
        "trancheDebtUSD": capital["_trancheDebtUSD"],
        "issuerTotalDebtUSD": capital["_modeledTotalDebtUSD"],
        "strategyDebtUSD": capital["_modeledTotalDebtUSD"],
        "debtRoundingResidualUSD": capital["_debtRoundingResidualUSD"],
        "roundingToleranceUSD": DEBT_ROUNDING_TOLERANCE_USD,
        "legacyOtherDebtUSD": capital["_otherDebtUSD"],
        "legacyDebtUSD": capital["_modeledTotalDebtUSD"] + capital["_otherDebtUSD"],
        "otherDebtScope": capital["_otherDebtScope"],
        "scopeNote": "Strategy Debt KPI includes convertibles only; Net BTC also subtracts other funded debt-like claims. otherDebtUSD is included in both Net BTC and legacy EV; operating liabilities are excluded.",
    }
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "observation": observation,
        "sourceFreshness": {
            "status": freshness_status,
            "capitalSnapshotAgeDays": age_days,
            "staleAfterDays": stale_after_days,
            "issuerSnapshotCarriedForward": age_days > 0,
            "note": "Issuer capital snapshots are retained until a later public disclosure; this is not represented as a new daily issuer disclosure.",
        },
        "qualityFlags": flags,
        "knowledgeBasis": knowledge_basis,
        "capitalReconciliation": reconciliation,
        "calculationStatus": "blocked" if capital["unmodeledSecurities"] else "calculated",
    }
    if capital["unmodeledSecurities"]:
        result["blockedReason"] = "Declared unmodeled securities could change claims or diluted shares"
        result["unmodeledSecurities"] = capital["unmodeledSecurities"]
        result["conversions"] = None
        result["metrics"] = {
            "legacyEvToGrossBtc": None,
            "basicEquityToGrossBtc": None,
            "strategyMnav": None,
            "strategyMnavReason": "blocked_unmodeled_security",
        }
        return result

    stock_price = price["stockPriceUSD"]
    btc_price = price["btcPriceUSD"]
    gross_btc_value = capital["btcHeld"] * btc_price
    total_debt = capital["_modeledTotalDebtUSD"]
    cash_assets = capital["usdReserve"] + capital["usdTreasuryCash"]
    basic_equity_value = capital["basicShares"] * stock_price
    legacy_ev = (basic_equity_value + total_debt + capital["_otherDebtUSD"] +
                 capital["preferredNotionalUSD"] - cash_assets)

    converted_debt_claim = 0.0
    converted_debt_shares = 0.0
    converted_ids = []
    for tranche in capital["debtTranches"]:
        if stock_price >= tranche["conversionPrice"]:
            converted_debt_claim += tranche["principal"]
            converted_debt_shares += tranche["conversionShares"]
            converted_ids.append(tranche["id"])
    strk_itm = stock_price >= capital["strk"]["conversionPrice"]
    converted_strk_claim = capital["strk"]["notionalUSD"] if strk_itm else 0.0
    converted_strk_shares = capital["strk"]["conversionShares"] if strk_itm else 0.0
    if strk_itm:
        converted_ids.append(capital["strk"]["id"])

    fdso = (capital["basicShares"] + capital["options"] + capital["rsuPsu"] +
            converted_debt_shares + converted_strk_shares)
    remaining_claims = (total_debt + capital["_otherDebtUSD"] + capital["preferredNotionalUSD"] -
                        converted_debt_claim - converted_strk_claim)
    net_btc = capital["btcHeld"] - (remaining_claims - cash_assets) / btc_price
    strategy_mnav = None if net_btc <= 0 else stock_price * fdso / (btc_price * net_btc)
    strategy_reason = "net_btc_nonpositive" if net_btc <= 0 else None

    result["conversions"] = {
        "itmSecurityIds": converted_ids,
        "removedDebtClaimUSD": converted_debt_claim,
        "removedStrkClaimUSD": converted_strk_claim,
        "addedDebtShares": converted_debt_shares,
        "addedStrkShares": converted_strk_shares,
        "fdso": fdso,
        "remainingClaimsUSD": remaining_claims,
        "netBtc": net_btc,
    }
    result["metrics"] = {
        "legacyEvToGrossBtc": legacy_ev / gross_btc_value,
        "basicEquityToGrossBtc": basic_equity_value / gross_btc_value,
        "strategyMnav": strategy_mnav,
        "strategyMnavReason": strategy_reason,
    }
    return result


def calculate_for_observation(snapshots: list[dict], price_observation: dict,
                              *, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS) -> dict:
    price = validate_price_observation(price_observation)
    capital = select_capital_snapshot(snapshots, price["asOf"])
    return calculate_refresh(capital, price, stale_after_days=stale_after_days)


def upsert_capital_snapshot(snapshots: list[dict], incoming: dict,
                            *, correction_reason: str | None = None) -> dict:
    """Return a new snapshot list and correction audit without mutating inputs."""
    validated_existing = [validate_capital_snapshot(x) for x in snapshots]
    new_snapshot = validate_capital_snapshot(incoming)
    same_as_of = [x for x in validated_existing if x["asOf"] == new_snapshot["asOf"]]
    if len(same_as_of) > 1:
        raise ContractError("duplicate_snapshot", f"multiple snapshots already exist for {new_snapshot['asOf']}")
    clean = lambda x: {k: v for k, v in x.items() if not k.startswith("_")}
    if not same_as_of:
        updated = validated_existing + [new_snapshot]
        updated.sort(key=lambda x: x["asOf"])
        return {"snapshots": [clean(x) for x in updated], "audit": [], "action": "inserted"}

    prior = same_as_of[0]
    if clean(prior) == clean(new_snapshot):
        return {"snapshots": [clean(x) for x in validated_existing], "audit": [], "action": "unchanged"}
    if not isinstance(correction_reason, str) or not correction_reason.strip():
        raise ContractError("correction_reason_required", "changing an existing asOf requires a correction reason")
    if _parse_instant(new_snapshot["readAt"], "incoming.readAt") <= _parse_instant(prior["readAt"], "prior.readAt"):
        raise ContractError("invalid_correction_order", "a correction must have a later readAt")
    updated = [new_snapshot if x["asOf"] == new_snapshot["asOf"] else x for x in validated_existing]
    updated.sort(key=lambda x: x["asOf"])
    audit = [{
        "schemaVersion": SCHEMA_VERSION,
        "asOf": new_snapshot["asOf"],
        "correctionReason": correction_reason.strip(),
        "correctedAt": new_snapshot["readAt"],
        "priorSnapshot": clean(prior),
        "replacementSnapshot": clean(new_snapshot),
    }]
    return {"snapshots": [clean(x) for x in updated], "audit": audit, "action": "corrected"}
