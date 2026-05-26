# Build Orchestrator — Dependency Analysis Repair

## Background

You are debugging a build orchestration system that analyzes build target dependencies to produce execution plans. The system reads a DAG (directed acyclic graph) of 15 build targets, computes which targets can build in parallel, assigns scheduling priorities, and identifies the critical path.

A recent refactor of the dependency analysis module (`/app/runtime/graph_analyzer.py`) introduced subtle bugs in the graph algorithms. The orchestrator runs without errors, produces output that *looks* reasonable, but the analysis results are wrong in ways that would cause incorrect scheduling in a real build system.

## System Layout

- **Entry point:** `/app/runtime/run_orchestrator.py`
- **Build targets:** `/app/runtime/build_targets.json` (15 targets forming a DAG)
- **Graph analyzer:** `/app/runtime/graph_analyzer.py` (the buggy module)
- **Plan builder:** `/app/runtime/plan_builder.py` (correct — uses analyzer results)
- **Output writer:** `/app/runtime/output_writer.py` (correct — writes JSON)
- **Output:** `/app/runtime/output/build_plan.json`

System-wide Python tooling and pytest are available.

## What the System Should Do

The orchestrator should:
1. Parse the build target DAG from `/app/runtime/build_targets.json`
2. Determine which pairs of targets are truly independent (no ordering constraint)
3. Compute scheduling priorities reflecting how critical each target is
4. Find the maximum set of targets that can safely execute in parallel
5. Identify the critical path (longest dependency chain)
6. Write a complete execution plan to `/app/runtime/output/build_plan.json`

## Observed Symptoms

After the refactor, the output has several issues:

- **The independent pair count is way too high.** The system reports ~84 independent pairs for a well-connected 15-node DAG. That's nearly 80% of all possible pairs — which makes no sense for targets that are clearly related through intermediate dependencies.

- **Priority scores don't reflect how critical a target is.** Root targets (which everything depends on) get the same tiny priority as mid-graph nodes. The scores are all in the range 0-2, which seems to ignore the actual cost of downstream work.

- **The parallel build set contains targets that clearly depend on each other.** The system claims 8 targets can run simultaneously, but inspection shows pairs in that set where one transitively depends on the other. Running these in parallel would cause build failures.

- **The fingerprint hash doesn't match** because it's computed from the incorrect analysis data.

## Expected Output Schema

The file `/app/runtime/output/build_plan.json` should contain:

```json
{
  "plan_version": "1.0",
  "total_targets": 15,
  "targets": [
    {
      "id": "target_X",
      "name": "...",
      "estimated_duration_ms": ...,
      "dependencies": [...],
      "priority": ...,
      "in_parallel_set": true/false,
      "on_critical_path": true/false
    }
  ],
  "analysis": {
    "independent_pair_count": ...,
    "critical_path": ["target_X", ...],
    "critical_path_length_ms": ...,
    "parallel_set": ["target_X", ...],
    "parallel_set_size": ...,
    "execution_stages": [[...], ...],
    "total_stages": ...,
    "makespan_ms": ...,
    "serial_time_ms": ...,
    "speedup_factor": ...
  },
  "priorities": {"target_X": ..., ...},
  "fingerprint": "sha256hex..."
}
```

## Your Task

Diagnose and fix the bugs in `/app/runtime/graph_analyzer.py`. The module contains three functions with plausible-but-wrong graph algorithms that interact with each other. Each function implements a valid graph theory concept — just not the right one for this use case.

Focus on:
- How independence between targets is determined
- How scheduling priority is computed
- How the maximum parallel execution set is selected

After applying your fix, regenerate the output by running:
```
python3 /app/runtime/run_orchestrator.py
```

The corrected plan should pass all validation checks in the test suite.
