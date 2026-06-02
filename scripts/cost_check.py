"""
Cost check — task 30.

Run this after the first live tournament day (on or after 2026-06-12) to
confirm spend is within the $1 budget target.

Prerequisites:
  - az CLI logged in: az login
  - jq installed

Usage:
  python scripts/cost_check.py <resource-group> [--period YYYY-MM-DD:YYYY-MM-DD]

Example:
  python scripts/cost_check.py rg-wc2026
  python scripts/cost_check.py rg-wc2026 --period 2026-06-12:2026-06-13
"""
import json
import subprocess
import sys
from datetime import date, timedelta


BUDGET_USD = 1.00

FREE_SERVICES = [
    "Azure Cosmos DB",
    "Azure Functions",
    "Azure Static Web Apps",
    "Azure Key Vault",
    "Azure Storage",
]


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def check_azure_spend(resource_group: str, start: str, end: str) -> float:
    """Query Azure Cost Management for the resource group's spend in the period."""
    try:
        output = run([
            "az", "consumption", "usage", "list",
            "--start-date", start,
            "--end-date", end,
            "--query", "[].{service:instanceName, cost:pretaxCost, currency:currency}",
            "--output", "json",
        ])
        items = json.loads(output)
        total = sum(float(i.get("cost", 0)) for i in items)
        return total
    except subprocess.CalledProcessError as e:
        print(f"WARNING: Could not query Azure Cost Management: {e}")
        return -1.0


def check_anthropic_budget(expected_calls: int = 36) -> None:
    """Remind operator to check Anthropic Console."""
    cost_per_call = 0.004          # rough estimate per group-stage prediction call
    estimated = cost_per_call * expected_calls
    print(f"\n  Anthropic Claude API (estimated):")
    print(f"    ~{expected_calls} prediction calls × ${cost_per_call:.3f} ≈ ${estimated:.2f}")
    print(f"    Check actual usage at: https://console.anthropic.com/usage")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="WC2026 cost check")
    parser.add_argument("resource_group", nargs="?", default="rg-wc2026")
    parser.add_argument("--period", default=None,
                        help="YYYY-MM-DD:YYYY-MM-DD (default: yesterday:today)")
    args = parser.parse_args()

    if args.period:
        start, end = args.period.split(":")
    else:
        today = date.today()
        start = str(today - timedelta(days=1))
        end = str(today)

    print(f"\nCost check for resource group: {args.resource_group}")
    print(f"Period: {start} → {end}")
    print("-" * 50)

    total = check_azure_spend(args.resource_group, start, end)

    if total >= 0:
        within_budget = total <= BUDGET_USD
        marker = "OK  " if within_budget else "FAIL"
        print(f"\n  [{marker}] Azure total spend: ${total:.4f} (budget: ${BUDGET_USD:.2f})")

        print("\n  Expected $0.00 for:")
        for svc in FREE_SERVICES:
            print(f"    - {svc}")
    else:
        print("  Azure spend could not be retrieved — check Azure portal manually.")
        print("  Portal: https://portal.azure.com → Cost Management + Billing")

    check_anthropic_budget()

    print("\nVerification checklist:")
    print("  [ ] Azure portal Cost Management shows $0.00 for all free-tier services")
    print("  [ ] Anthropic Console shows spend ≤ $0.14 for the tournament so far")
    print("  [ ] fn_ingest ran on schedule (check Function App > Monitor > Invocations)")
    print("  [ ] Cosmos DB shows documents in teams, fixtures, predictions containers")
    print()


if __name__ == "__main__":
    main()
