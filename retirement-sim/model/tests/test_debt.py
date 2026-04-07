"""Debt module unit tests — amortization, payments, balances, and tax deduction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parents[2]
if str(MODEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MODEL_ROOT))

from model.debt import (
    DebtParams,
    apply_debt_strategy,
    debt_annual_interest,
    debt_annual_payment,
    debt_end_of_year_balance,
    debt_is_active,
    debt_monthly_payment,
    student_loan_interest_deduction,
)


class TestDebtMonthlyPayment(unittest.TestCase):

    def test_minimum_only(self):
        d = DebtParams(enabled=True, minimum_payment=500, extra_monthly_payment=0)
        self.assertAlmostEqual(debt_monthly_payment(d), 500)

    def test_with_extra(self):
        d = DebtParams(enabled=True, minimum_payment=500, extra_monthly_payment=200)
        self.assertAlmostEqual(debt_monthly_payment(d), 700)


class TestDebtAnnualPayment(unittest.TestCase):

    def test_zero_balance_returns_zero(self):
        d = DebtParams(enabled=True, minimum_payment=500)
        self.assertEqual(debt_annual_payment(d, 0.0), 0.0)

    def test_disabled_returns_zero(self):
        d = DebtParams(enabled=False, minimum_payment=500, current_balance=10000)
        self.assertEqual(debt_annual_payment(d, 10000), 0.0)

    def test_full_year_payments(self):
        """$10,000 at 6%, $500/mo → 12 payments (balance won't be fully repaid)."""
        d = DebtParams(enabled=True, current_balance=10000, interest_rate=0.06,
                       minimum_payment=500)
        annual = debt_annual_payment(d, 10000)
        # 12 × $500 = $6,000 (balance is large enough that payments don't exhaust it)
        self.assertAlmostEqual(annual, 6000, places=0)

    def test_small_balance_caps_payment(self):
        """If balance is smaller than 12 months of payments, caps at balance + interest."""
        d = DebtParams(enabled=True, current_balance=1000, interest_rate=0.06,
                       minimum_payment=500)
        annual = debt_annual_payment(d, 1000)
        # Should pay off in ~2 months. Total ≈ $1,000 + ~$8 interest = ~$1,008
        self.assertGreater(annual, 1000)
        self.assertLess(annual, 1100)  # should be close to principal + a little interest

    def test_zero_interest_rate(self):
        """No interest — annual payment = min(12 * payment, balance)."""
        d = DebtParams(enabled=True, current_balance=5000, interest_rate=0.0,
                       minimum_payment=500)
        annual = debt_annual_payment(d, 5000)
        self.assertAlmostEqual(annual, 5000, places=2)


class TestDebtEndOfYearBalance(unittest.TestCase):

    def test_zero_balance(self):
        d = DebtParams(enabled=True, minimum_payment=500)
        self.assertEqual(debt_end_of_year_balance(d, 0.0), 0.0)

    def test_large_balance_partially_paid(self):
        """$50,000 at 7%, $600/mo → balance should decrease but still be > 0."""
        d = DebtParams(enabled=True, current_balance=50000, interest_rate=0.07,
                       minimum_payment=600)
        end_bal = debt_end_of_year_balance(d, 50000)
        # $600/mo × 12 = $7,200 in payments, ~$3,300 interest → ~$3,900 principal reduction
        self.assertGreater(end_bal, 40000)
        self.assertLess(end_bal, 50000)

    def test_fully_paid_off(self):
        """Small balance, large payments → should reach 0."""
        d = DebtParams(enabled=True, current_balance=1000, interest_rate=0.05,
                       minimum_payment=500)
        end_bal = debt_end_of_year_balance(d, 1000)
        self.assertAlmostEqual(end_bal, 0.0, places=2)

    def test_balance_decreases_each_year(self):
        """Balance should strictly decrease year-over-year for a paying debt."""
        d = DebtParams(enabled=True, current_balance=30000, interest_rate=0.065,
                       minimum_payment=400)
        bal = 30000
        for _ in range(5):
            new_bal = debt_end_of_year_balance(d, bal)
            self.assertLess(new_bal, bal)
            bal = new_bal


class TestDebtAnnualInterest(unittest.TestCase):

    def test_zero_rate(self):
        d = DebtParams(enabled=True, current_balance=10000, interest_rate=0.0,
                       minimum_payment=500)
        self.assertAlmostEqual(debt_annual_interest(d, 10000), 0.0)

    def test_standard_interest(self):
        """$20,000 at 6%, $400/mo. First month interest = $100. Year total ≈ $1,100."""
        d = DebtParams(enabled=True, current_balance=20000, interest_rate=0.06,
                       minimum_payment=400)
        interest = debt_annual_interest(d, 20000)
        # Annual interest on a $20K loan at 6% is roughly $1,100 (declining balance)
        self.assertGreater(interest, 900)
        self.assertLess(interest, 1300)

    def test_high_rate_credit_card(self):
        """$10,000 at 20%, $200/mo (barely above minimum)."""
        d = DebtParams(enabled=True, current_balance=10000, interest_rate=0.20,
                       minimum_payment=200)
        interest = debt_annual_interest(d, 10000)
        # ~$167/mo interest initially, nearly all payment goes to interest
        self.assertGreater(interest, 1800)
        self.assertLess(interest, 2100)


class TestDebtIsActive(unittest.TestCase):

    def test_active(self):
        d = DebtParams(enabled=True, current_balance=5000)
        self.assertTrue(debt_is_active(d, 5000))

    def test_disabled(self):
        d = DebtParams(enabled=False, current_balance=5000)
        self.assertFalse(debt_is_active(d, 5000))

    def test_zero_balance(self):
        d = DebtParams(enabled=True, current_balance=0)
        self.assertFalse(debt_is_active(d, 0))

    def test_near_zero_balance(self):
        d = DebtParams(enabled=True, current_balance=0.005)
        self.assertFalse(debt_is_active(d, 0.005))


class TestStudentLoanInterestDeduction(unittest.TestCase):

    def test_no_student_loans(self):
        debts = [
            DebtParams(enabled=True, category="Credit Card", current_balance=5000,
                       interest_rate=0.20, minimum_payment=200),
        ]
        ded = student_loan_interest_deduction(debts, [5000])
        self.assertEqual(ded, 0.0)

    def test_student_loan_under_cap(self):
        debts = [
            DebtParams(enabled=True, category="Student Loan", current_balance=20000,
                       interest_rate=0.06, minimum_payment=400),
        ]
        ded = student_loan_interest_deduction(debts, [20000])
        # Interest on $20K at 6% ≈ $1,100 — under $2,500 cap
        self.assertGreater(ded, 900)
        self.assertLess(ded, 2500)

    def test_student_loan_capped_at_2500(self):
        """Large student loan → interest exceeds $2,500 cap."""
        debts = [
            DebtParams(enabled=True, category="Student Loan", current_balance=100000,
                       interest_rate=0.07, minimum_payment=500),
        ]
        ded = student_loan_interest_deduction(debts, [100000])
        self.assertAlmostEqual(ded, 2500, places=2)

    def test_mixed_debts(self):
        """Only student loan interest counts, not credit card."""
        debts = [
            DebtParams(enabled=True, category="Credit Card", current_balance=10000,
                       interest_rate=0.20, minimum_payment=200),
            DebtParams(enabled=True, category="Student Loan", current_balance=15000,
                       interest_rate=0.05, minimum_payment=300),
        ]
        balances = [10000, 15000]
        ded = student_loan_interest_deduction(debts, balances)
        # Only student loan interest counts (~$700 on $15K at 5%)
        self.assertGreater(ded, 500)
        self.assertLess(ded, 2500)


class TestPayoffStrategy(unittest.TestCase):
    """Tests for avalanche/snowball payoff strategies."""

    def _two_debts(self):
        """Helper: credit card (20%, $5K) and auto loan (6%, $15K)."""
        return [
            DebtParams(enabled=True, label="Visa", category="Credit Card",
                       current_balance=5000, interest_rate=0.20, minimum_payment=200),
            DebtParams(enabled=True, label="Honda", category="Auto Loan",
                       current_balance=15000, interest_rate=0.06, minimum_payment=300),
            DebtParams(enabled=False),  # slot 3 unused
        ]

    def test_none_strategy_matches_independent(self):
        """Strategy 'none' should produce same results as individual debt math."""
        debts = self._two_debts()
        balances = [5000, 15000, 0]
        new_bals, payments, interest = apply_debt_strategy(debts, balances, "none", 0)
        # Each debt pays independently at its own min + extra
        self.assertAlmostEqual(payments[0], debt_annual_payment(debts[0], 5000), places=2)
        self.assertAlmostEqual(payments[1], debt_annual_payment(debts[1], 15000), places=2)
        self.assertEqual(payments[2], 0.0)

    def test_avalanche_concentrates_on_highest_rate(self):
        """Avalanche should put extra budget on the 20% credit card first."""
        debts = self._two_debts()
        balances = [5000, 15000, 0]
        # $300/mo extra budget → all goes to Visa (20% rate)
        new_bals_aval, payments_aval, _ = apply_debt_strategy(
            debts, balances, "avalanche", 300,
        )
        # Compare to no strategy
        new_bals_none, payments_none, _ = apply_debt_strategy(
            debts, balances, "none", 0,
        )
        # Avalanche should pay off the credit card faster
        self.assertLess(new_bals_aval[0], new_bals_none[0])
        # Auto loan gets only minimum, so balance should be similar
        self.assertAlmostEqual(new_bals_aval[1], new_bals_none[1], delta=100)

    def test_snowball_concentrates_on_lowest_balance(self):
        """Snowball should put extra budget on the $5K credit card (lowest balance)."""
        debts = self._two_debts()
        balances = [5000, 15000, 0]
        new_bals_snow, payments_snow, _ = apply_debt_strategy(
            debts, balances, "snowball", 300,
        )
        # Credit card ($5K) is lowest balance AND happens to be highest rate here,
        # so snowball targets it too. Verify it pays down faster.
        new_bals_none, _, _ = apply_debt_strategy(debts, balances, "none", 0)
        self.assertLess(new_bals_snow[0], new_bals_none[0])

    def test_avalanche_vs_snowball_different_target(self):
        """When lowest balance != highest rate, strategies diverge."""
        debts = [
            DebtParams(enabled=True, label="Small CC", category="Credit Card",
                       current_balance=2000, interest_rate=0.15, minimum_payment=100),
            DebtParams(enabled=True, label="Big CC", category="Credit Card",
                       current_balance=20000, interest_rate=0.22, minimum_payment=400),
            DebtParams(enabled=False),
        ]
        balances = [2000, 20000, 0]
        bals_aval, _, _ = apply_debt_strategy(debts, balances, "avalanche", 200)
        bals_snow, _, _ = apply_debt_strategy(debts, balances, "snowball", 200)
        # Avalanche targets Big CC (22%) → Big CC balance lower in avalanche
        self.assertLess(bals_aval[1], bals_snow[1])
        # Snowball targets Small CC ($2K) → Small CC balance lower in snowball
        self.assertLess(bals_snow[0], bals_aval[0])

    def test_cascade_freed_minimums(self):
        """When a debt pays off, its minimum should cascade to the next target."""
        debts = [
            DebtParams(enabled=True, label="Small", category="Personal Loan",
                       current_balance=500, interest_rate=0.05, minimum_payment=200),
            DebtParams(enabled=True, label="Big", category="Auto Loan",
                       current_balance=20000, interest_rate=0.07, minimum_payment=300),
            DebtParams(enabled=False),
        ]
        balances = [500, 20000, 0]
        # $100 extra → Small pays off in ~3 months, then $200 min + $100 extra cascade to Big
        bals, payments, _ = apply_debt_strategy(debts, balances, "avalanche", 100)
        # Small should be fully paid off
        self.assertAlmostEqual(bals[0], 0.0, places=2)
        # Big should have received more than just its minimum (cascade effect)
        bals_no_cascade, _, _ = apply_debt_strategy(debts, balances, "none", 0)
        self.assertLess(bals[1], bals_no_cascade[1])

    def test_strategy_with_projection(self):
        """Avalanche strategy should produce better NW than no strategy."""
        from model.inputs import SeedCase
        from model.projection import run_projection

        debts_common = dict(
            debt_1=DebtParams(enabled=True, label="CC", category="Credit Card",
                              current_balance=10000, interest_rate=0.20, minimum_payment=300),
            debt_2=DebtParams(enabled=True, label="Auto", category="Auto Loan",
                              current_balance=15000, interest_rate=0.06, minimum_payment=350),
        )
        seed_none = SeedCase(**debts_common, debt_payoff_strategy="none")
        seed_aval = SeedCase(**debts_common, debt_payoff_strategy="avalanche",
                             debt_extra_monthly_budget=200)
        records_none = run_projection(seed_none)
        records_aval = run_projection(seed_aval)
        # Avalanche with extra budget should result in higher end NW
        self.assertGreater(records_aval[-1].total_nw, records_none[-1].total_nw)


class TestProjectionIntegration(unittest.TestCase):
    """Verify debt integrates correctly with the projection engine."""

    def test_student_loan_deduction_reduces_tax(self):
        """Student loan interest should reduce taxable income → lower tax."""
        from model.inputs import SeedCase
        from model.projection import run_projection

        seed_no_loan = SeedCase()
        seed_with_loan = SeedCase(
            debt_1=DebtParams(
                enabled=True, label="Student Loan", category="Student Loan",
                current_balance=40000, interest_rate=0.06,
                minimum_payment=450,
            ),
        )
        records_no = run_projection(seed_no_loan)
        records_with = run_projection(seed_with_loan)
        # Year 1: student loan interest ~$2,300. Deduction reduces taxable income.
        # Federal tax should be lower with the deduction (holding all else equal
        # except the debt payments also reduce net savings, which could affect
        # the phase determination). Compare year 1 taxable income directly.
        self.assertLess(records_with[0].taxable_income, records_no[0].taxable_income)

    def test_retirement_trigger_accounts_for_debt(self):
        """Debt should delay retirement by reducing spendable NW."""
        from model.inputs import SeedCase
        from model.inputs import RetirementTriggerParams
        from model.projection import run_projection

        # Low retirement target so both plans retire, but debt delays it
        trigger = RetirementTriggerParams(net_worth_target=400_000)
        seed_no_debt = SeedCase(retirement=trigger)
        seed_with_debt = SeedCase(
            retirement=trigger,
            debt_1=DebtParams(
                enabled=True, label="Big Loan", category="Personal Loan",
                current_balance=100_000, interest_rate=0.08,
                minimum_payment=800,
            ),
        )
        records_no = run_projection(seed_no_debt)
        records_with = run_projection(seed_with_debt)
        retire_age_no = next((r.age for r in records_no if r.phase == "Retired"), None)
        retire_age_with = next((r.age for r in records_with if r.phase == "Retired"), None)
        # Debt should delay retirement
        self.assertIsNotNone(retire_age_no)
        self.assertIsNotNone(retire_age_with)
        self.assertGreater(retire_age_with, retire_age_no)

    def test_debt_reduces_net_worth(self):
        """A plan with debt should have lower NW than one without."""
        from model.inputs import SeedCase
        from model.projection import run_projection

        # Baseline: no debt
        seed_no_debt = SeedCase()
        records_no_debt = run_projection(seed_no_debt)

        # With debt: $20K credit card at 20%
        seed_with_debt = SeedCase(
            debt_1=DebtParams(
                enabled=True, label="Visa", category="Credit Card",
                current_balance=20000, interest_rate=0.20,
                minimum_payment=500,
            ),
        )
        records_with_debt = run_projection(seed_with_debt)

        # Net worth should be lower with debt
        self.assertLess(
            records_with_debt[-1].total_nw,
            records_no_debt[-1].total_nw,
        )

    def test_debt_payments_appear_in_expenses(self):
        """Debt payments should increase living expenses."""
        from model.inputs import SeedCase
        from model.projection import run_projection

        seed = SeedCase(
            debt_1=DebtParams(
                enabled=True, label="Auto Loan", category="Auto Loan",
                current_balance=25000, interest_rate=0.065,
                minimum_payment=500,
            ),
        )
        records = run_projection(seed)
        # First year should have non-zero debt expense
        self.assertGreater(records[0].expense_debt, 0)
        # expense_debt should equal 12 × $500 = $6,000 (balance large enough)
        self.assertAlmostEqual(records[0].expense_debt, 6000, delta=50)

    def test_debt_pays_off_and_expenses_drop(self):
        """Once debt is paid off, expense_debt should drop to zero."""
        from model.inputs import SeedCase
        from model.projection import run_projection

        # Small debt that pays off in ~1 year
        seed = SeedCase(
            debt_1=DebtParams(
                enabled=True, label="Small Loan", category="Personal Loan",
                current_balance=3000, interest_rate=0.05,
                minimum_payment=500,
            ),
        )
        records = run_projection(seed)
        # After a couple years, debt should be gone
        self.assertAlmostEqual(records[2].debt_1_balance, 0.0, places=2)
        self.assertAlmostEqual(records[2].expense_debt, 0.0, places=2)

    def test_no_debt_baseline_unchanged(self):
        """With no debts enabled, projection should be identical to before."""
        from model.inputs import SeedCase
        from model.projection import run_projection

        seed = SeedCase()
        records = run_projection(seed)
        for r in records:
            self.assertEqual(r.expense_debt, 0.0)
            self.assertEqual(r.total_debt_balance, 0.0)


if __name__ == "__main__":
    unittest.main()
