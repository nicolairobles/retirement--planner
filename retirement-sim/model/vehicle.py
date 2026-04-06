"""
Vehicle replacement schedule — periodic outflows for replacement cars.

Mirrors Excel Projection column N:
  IF(IncludeVehicle AND year >= FirstVehicleYear AND age < StopDrivingAge
     AND (year - FirstVehicleYear) % Interval == 0,
     VehicleCost * (1+Inflation)^(year - base_year),
     0)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleParams:
    """Vehicle replacement parameters."""
    include: bool = True                 # in_IncludeVehicle
    cost_base_year: float = 40_000.0      # in_VehicleCost (base-year dollars)
    interval_years: int = 12              # in_VehicleInterval
    first_purchase_year: int = 2030       # in_FirstVehicleYear
    stop_driving_age: int = 80            # in_StopDrivingAge


def vehicle_cost(year: int, age: int, params: VehicleParams, inflation: float, base_year: int) -> float:
    """Return vehicle outflow for a given year (0 if no purchase that year).

    A purchase happens every `interval_years` starting from `first_purchase_year`,
    stopping once age reaches stop_driving_age.
    """
    if not params.include:
        return 0.0
    if year < params.first_purchase_year:
        return 0.0
    if age >= params.stop_driving_age:
        return 0.0
    if (year - params.first_purchase_year) % params.interval_years != 0:
        return 0.0
    return params.cost_base_year * (1.0 + inflation) ** (year - base_year)
