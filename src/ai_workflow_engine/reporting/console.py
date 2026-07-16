from rich.console import Console
from rich.table import Table

from ai_workflow_engine.result import CheckResult, VerificationReport


def print_check(result: CheckResult, console: Console) -> None:
    color = {"PASS": "green", "FAIL": "red", "ERROR": "bold red"}[result.status]
    console.print(f"[{color}]{result.status}[/{color}] {result.check_name}: {result.summary}")
    for finding in result.findings:
        location = f" ({finding.path})" if finding.path else ""
        console.print(f"  - {finding.code}{location}: {finding.message}")
    if result.remediation_hint:
        console.print(f"  Hint: {result.remediation_hint}")


def print_report(report: VerificationReport, console: Console) -> None:
    table = Table(title=f"Verification: {report.project_id}")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Summary")
    for result in report.checks:
        table.add_row(result.check_name, result.status, result.summary)
    console.print(table)
    console.print(f"Verdict: {report.status}")
