"""Single Typer registry for the ConformDAG command adapters."""

import typer

from . import agent, benchmark, fix, pack, platform, policy, scan, utility

app = typer.Typer(add_completion=False, no_args_is_help=True)
policy_app = typer.Typer(add_completion=False, no_args_is_help=True)
agent_app = typer.Typer(add_completion=False, no_args_is_help=True)
baseline_app = typer.Typer(add_completion=False, no_args_is_help=True)
pack_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(policy_app, name="policy")
app.add_typer(agent_app, name="agent")
app.add_typer(baseline_app, name="baseline")
app.add_typer(pack_app, name="pack")

policy_app.command("show")(policy.policy_show)
policy_app.command("review")(policy.policy_review)
policy_app.command("explain")(policy.policy_explain)
policy_app.command("reference")(policy.policy_reference)
policy_app.command("hash")(policy.policy_hash)
policy_app.command("new")(policy.policy_new)
agent_app.command("run")(agent.agent_run)
agent_app.command("policy-review")(agent.agent_policy_review)
baseline_app.command("set")(platform.baseline_set)
pack_app.command("pull")(pack.pack_pull)

app.command("init")(utility.init)
app.command("doctor")(utility.doctor)
app.command("validate-policies")(policy.validate_policies)
app.command("list-policies")(policy.list_policies)
app.command("explain", hidden=True)(policy.explain)
app.command("scan")(scan.scan)
app.command("fix")(fix.fix)
app.command("version")(utility.version)
app.command("serve")(platform.serve)
app.command("worker")(platform.worker_command)
app.command("benchmark")(benchmark.benchmark)
