"""
Seed case loader for the Streamlit app.

Loads hypothetical personas from demo_cases.json and builds a SeedCase
for the Python model. Supports variable current_age per persona (unlike
the eval-suite version which assumes age 37 from the workbook).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "retirement-sim"))

from model.allocation import AllocationParams
from model.expenses import ExpenseParams, PropertyParams
from model.income import DisabilityParams, SSParams
from model.expenses import HealthcareParams, LTCParams
from model.inputs import (
    CashReserveParams,
    CustomAssetBucket,
    OtherIncomeStream,
    RetirementTriggerParams,
    RothConversionParams,
    SalarySchedule,
    SeedCase,
    StartingBalances,
)
from model.returns import ReturnParams
from model.tax import TaxParams
from model.vehicle import VehicleParams

DEMO_CASES_PATH = APP_ROOT / "helpers" / "demo_cases.json"
BASE_YEAR = 2025


def load_demo_cases() -> list[dict]:
    """Load demo personas from JSON."""
    with DEMO_CASES_PATH.open() as f:
        data = json.load(f)
    return data["cases"]


def build_seedcase_from_inputs(inputs: dict, current_age: int = 35) -> SeedCase:
    """Build a SeedCase from an inputs dict.

    `current_age` defaults to 35 (Alex persona). Override per persona.
    """
    ss_age = inputs.get("in_SSAge", 67)
    ss_start_year = BASE_YEAR + ss_age - current_age

    return SeedCase(
        base_year=BASE_YEAR,
        current_age=current_age,
        end_age=int(inputs.get("in_EndAge", 90)),
        starting_balances=StartingBalances(
            k401=float(inputs.get("in_401kStart", 0)),
            roth_401k=float(inputs.get("in_Roth401kStart", 0)),
            investments=float(inputs.get("in_InvestStart", 0)),
            cash=float(inputs.get("in_CashStart", 0)),
            crypto=float(inputs.get("in_CryptoStart", 0)),
        ),
        salary=SalarySchedule(
            year1=float(inputs.get("in_Year1Salary", inputs.get("in_Salary", 0))),
            year2=float(inputs.get("in_Year2Salary", inputs.get("in_Salary", 0))),
            year3=float(inputs.get("in_Year3Salary", inputs.get("in_Salary", 0))),
            year4=float(inputs.get("in_Year4Salary", inputs.get("in_Salary", 0))),
            growth_rate=float(inputs.get("in_SalaryGrowth", 0.03)),
            annual_401k_contrib=float(inputs.get("in_401kContrib", 0)),
            roth_contribution_pct=float(inputs.get("in_RothContribPct", 0.0)),
        ),
        expenses=ExpenseParams(
            monthly_non_housing=float(inputs.get("in_MonthlyNonHousing", 0)),
            monthly_rent=float(inputs.get("in_MonthlyRent", 0)),
            inflation=float(inputs.get("in_Inflation", 0.03)),
            base_year=BASE_YEAR,
        ),
        prop=PropertyParams(
            buy_property=inputs.get("in_BuyProperty", "No") == "Yes",
            purchase_year=int(inputs.get("in_PropertyYear", 2035)),
            cost=float(inputs.get("in_PropertyCost", 350000)),
            monthly_ownership_cost=_compute_ownership_cost(inputs),
            appreciation=float(inputs.get("in_PropertyAppreciation", 0.04)),
            mortgage=inputs.get("in_MortgageYN", "No") == "Yes",
            down_payment_pct=float(inputs.get("in_DownPaymentPct", 0.20)),
            mortgage_rate=float(inputs.get("in_MortgageRate", 0.065)),
            mortgage_term_years=int(inputs.get("in_MortgageTerm", 30)),
            closing_cost_pct=float(inputs.get("in_ClosingCostPct", 0.025)),
            selling_cost_pct=float(inputs.get("in_SellingCostPct", 0.06)),
        ),
        returns=ReturnParams(
            stock_return=float(inputs.get("in_StockReturn", 0.07)),
            bond_return=float(inputs.get("in_BondReturn", 0.04)),
            crypto_return=float(inputs.get("in_CryptoReturn", 0.05)),
            cash_return=float(inputs.get("in_CashReturn", 0.02)),
        ),
        allocation=AllocationParams(
            crypto_pct=float(inputs.get("in_CryptoPct", 0.05)),
            max_bonds=float(inputs.get("in_MaxBonds", 0.40)),
            use_fixed_mix=inputs.get("in_UseFixedMix", "No") == "Yes",
            fixed_stock_pct=float(inputs.get("in_FixedStockPct", 0.60)),
        ),
        cash_reserve=CashReserveParams(
            months=int(inputs.get("in_CashReserveMonths", 6)),
            cash_return=float(inputs.get("in_CashReturn", 0.02)),
        ),
        ss=SSParams(
            eligible=inputs.get("in_SSEligible", "Yes") == "Yes",
            benefit_monthly_today=float(inputs.get("in_SSBenefit", 2600)),
            cola=float(inputs.get("in_SSCola", 0.02)),
            start_age=int(ss_age),
            current_age=current_age,
            base_year=BASE_YEAR,
        ),
        disability=DisabilityParams(
            eligible=inputs.get("in_DisabYN", "No") == "Yes",
            benefit_monthly=float(inputs.get("in_DisabBenefit", 0)),
            cola=float(inputs.get("in_DisabCola", 0.025)),
            start_year=int(inputs.get("in_DisabStartYear", 2030)),
            end_year=ss_start_year,
        ),
        tax=TaxParams(
            std_deduction_base=float(inputs.get("in_StdDeduction", 15000)),
            bracket_indexation=float(inputs.get("in_BracketIndexation", 0.025)),
            base_year=BASE_YEAR,
        ),
        retirement=RetirementTriggerParams(
            net_worth_target=float(inputs.get("in_RetirementTarget", 1000000)),
            k401_access_age=float(inputs.get("in_401kAccessAge", 59.5)),
        ),
        vehicle=VehicleParams(
            include=inputs.get("in_IncludeVehicle", "Yes") == "Yes",
            cost_base_year=float(inputs.get("in_VehicleCost", 35000)),
            interval_years=int(inputs.get("in_VehicleInterval", 12)),
            first_purchase_year=int(inputs.get("in_FirstVehicleYear", 2030)),
            stop_driving_age=int(inputs.get("in_StopDrivingAge", 80)),
        ),
        other_income_1=OtherIncomeStream(
            enabled=inputs.get("in_Other1Enabled", "No") == "Yes",
            label=inputs.get("in_Other1Label", "Other Income 1"),
            monthly_today=float(inputs.get("in_Other1Monthly", 0)),
            cola=float(inputs.get("in_Other1Cola", 0.02)),
            start_year=int(inputs.get("in_Other1StartYear", 2030)),
            end_year=int(inputs.get("in_Other1EndYear", 2090)),
            taxable=inputs.get("in_Other1Taxable", "Yes") == "Yes",
        ),
        other_income_2=OtherIncomeStream(
            enabled=inputs.get("in_Other2Enabled", "No") == "Yes",
            label=inputs.get("in_Other2Label", "Other Income 2"),
            monthly_today=float(inputs.get("in_Other2Monthly", 0)),
            cola=float(inputs.get("in_Other2Cola", 0.02)),
            start_year=int(inputs.get("in_Other2StartYear", 2030)),
            end_year=int(inputs.get("in_Other2EndYear", 2090)),
            taxable=inputs.get("in_Other2Taxable", "Yes") == "Yes",
        ),
        custom_asset_1=_custom_asset_from_inputs(inputs, 1),
        custom_asset_2=_custom_asset_from_inputs(inputs, 2),
        custom_asset_3=_custom_asset_from_inputs(inputs, 3),
        roth_conversion=RothConversionParams(
            enabled=inputs.get("in_RothConvEnabled", "No") == "Yes",
            amount_per_year=float(inputs.get("in_RothConvAmount", 0)),
            start_year=int(inputs.get("in_RothConvStartYear", 2040)),
            end_year=int(inputs.get("in_RothConvEndYear", 2050)),
        ),
        healthcare=HealthcareParams(
            enabled=inputs.get("in_HealthcareEnabled", "No") == "Yes",
            monthly_pre_medicare=float(inputs.get("in_HealthcarePreMedicare", 1000)),
            monthly_medicare=float(inputs.get("in_HealthcareMedicare", 600)),
            medicare_age=int(inputs.get("in_HealthcareMedicareAge", 65)),
            healthcare_inflation=float(inputs.get("in_HealthcareInflation", 0.05)),
        ),
        ltc=LTCParams(
            enabled=inputs.get("in_LTCEnabled", "No") == "Yes",
            monthly_cost=float(inputs.get("in_LTCMonthly", 8000)),
            start_age=int(inputs.get("in_LTCStartAge", 82)),
            duration_years=int(inputs.get("in_LTCDuration", 3)),
        ),
    )


def _compute_ownership_cost(inputs: dict) -> float:
    """Compute monthly ownership cost from component inputs.

    Breakdown: property tax + home insurance + maintenance + HOA. All %
    rates are applied to property cost. Provides sensible national-average
    defaults so the user faces inputs they can actually reason about.

    Defaults (national averages):
      - Property tax: 1.1% of value/yr (varies 0.3% HI to 2.5% NJ/TX)
      - Home insurance: 0.4% of value/yr
      - Maintenance: 1.0% of value/yr (industry rule of thumb)
      - HOA: $0/mo (only if applicable)

    Legacy fallback: if `in_MonthlyOwnershipCost` is present AND none of the
    component keys are, use that value directly (backward compat for old
    saved scenarios). Otherwise compute from components.
    """
    # Legacy single-field path — only if NO component keys are set
    has_components = any(
        k in inputs for k in (
            "in_PropertyTaxRate", "in_HomeInsuranceRate",
            "in_MaintenanceRate", "in_MonthlyHOA",
        )
    )
    if not has_components and "in_MonthlyOwnershipCost" in inputs:
        return float(inputs["in_MonthlyOwnershipCost"])

    cost = float(inputs.get("in_PropertyCost", 350_000))
    tax_rate = float(inputs.get("in_PropertyTaxRate", 0.011))
    ins_rate = float(inputs.get("in_HomeInsuranceRate", 0.004))
    maint_rate = float(inputs.get("in_MaintenanceRate", 0.010))
    hoa = float(inputs.get("in_MonthlyHOA", 0))

    annual_pct_cost = cost * (tax_rate + ins_rate + maint_rate)
    return annual_pct_cost / 12.0 + hoa


def _custom_asset_from_inputs(inputs: dict, n: int) -> CustomAssetBucket:
    """Extract a CustomAssetBucket from app input keys."""
    return CustomAssetBucket(
        enabled=inputs.get(f"in_Custom{n}Enabled", "No") == "Yes",
        name=inputs.get(f"in_Custom{n}Name", f"Custom Asset {n}"),
        starting_balance=float(inputs.get(f"in_Custom{n}Start", 0)),
        annual_contribution=float(inputs.get(f"in_Custom{n}Contrib", 0)),
        return_rate=float(inputs.get(f"in_Custom{n}Return", 0.05)),
        liquid=inputs.get(f"in_Custom{n}Liquid", "Yes") == "Yes",
        draw_priority=int(inputs.get(f"in_Custom{n}DrawPriority", 2)),
    )


# Persona → implied current age (inferred from persona tagline)
PERSONA_AGES = {
    "alex-mid-career": 35,
    "jordan-late-start": 45,
    "sam-early-career": 28,
}
