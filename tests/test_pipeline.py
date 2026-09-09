import asyncio
import time

import pytest

from src.edwh.pipeline import Run, Step, StepFailedError, drive
from src.edwh.tui import plain, renderer_for


def collect(pipeline, max_parallel: int = 4) -> Run:
    """Run a pipeline with a renderer that does nothing, and hand back the finished Run."""
    return asyncio.run(drive(pipeline, lambda _: None, interval=0.005, max_parallel=max_parallel))


# -- shell steps --------------------------------------------------------------------------


def test_sh_parses_status_lines_and_keeps_log_lines():
    async def pipeline(run: Run):
        await run.sh("probe", "echo ':: reading .env'; echo 'plain output'; echo ':: done'")

    step = collect(pipeline).steps[0]

    assert step.state == "done"
    assert step.status == "done"
    assert step.lines == ["plain output"], ":: lines set the status but are not logged"
    assert "reading .env" in step.out


def test_sh_marks_a_nonzero_exit_as_failed():
    async def pipeline(run: Run):
        await run.sh("boom", "echo ':: about to fail'; exit 3")

    run = collect(pipeline)

    assert run.steps[0].state == "failed"
    assert run.steps[0].status == "exit 3"
    assert run.failed == run.steps


def test_sh_runs_in_the_given_cwd(tmp_path):
    (tmp_path / "marker").write_text("hi")

    async def pipeline(run: Run):
        await run.sh("ls", "cat marker", cwd=tmp_path)

    assert collect(pipeline).steps[0].out.strip() == "hi"


def test_sh_passes_extra_env_on_top_of_os_environ():
    async def pipeline(run: Run):
        await run.sh("env", "echo $EDWH_TEST_MARKER", env={"EDWH_TEST_MARKER": "yes"})

    assert collect(pipeline).steps[0].out.strip() == "yes"


# -- python steps -------------------------------------------------------------------------


def test_fn_reports_status_and_completes():
    def work(step: Step):
        step.report("halfway")

    async def pipeline(run: Run):
        await run.fn("python work", work)

    step = collect(pipeline).steps[0]
    assert step.state == "done"
    assert step.status == "halfway"


def test_fn_failure_is_recorded_without_killing_the_group():
    def boom(_: Step):
        raise ValueError("nope")

    def fine(step: Step):
        step.report("all good")

    async def pipeline(run: Run):
        await run.fn_group([("boom", boom), ("fine", fine)])

    run = collect(pipeline)
    boom_step, fine_step = run.steps

    assert boom_step.state == "failed"
    assert "nope" in boom_step.status
    assert isinstance(boom_step.error, ValueError)
    assert fine_step.state == "done", "a sibling failure must not cancel the rest of the group"


def test_check_raises_on_a_failed_step_and_drive_swallows_it():
    ran_after = []

    async def pipeline(run: Run):
        await run.sh("boom", "exit 1")
        run.check()
        ran_after.append(True)

    run = collect(pipeline)

    assert not ran_after, "check() must stop the pipeline"
    assert run.done, "drive() still finishes cleanly so the caller can inspect the run"
    assert len(run.failed) == 1


def test_check_is_a_noop_while_everything_succeeds():
    run = Run()
    run.check()  # no steps
    step = Step("x", 1)
    step.state = "done"
    run.steps.append(step)
    run.check()


def test_step_failed_error_is_raised_by_check():
    run = Run()
    step = Step("x", 1)
    step.state = "failed"
    step.status = "exit 1"
    run.steps.append(step)

    with pytest.raises(StepFailedError, match="x: exit 1"):
        run.check()


# -- concurrency --------------------------------------------------------------------------


def test_max_parallel_holds_the_third_sibling_queued():
    seen_states = []

    async def pipeline(run: Run):
        async def watch():
            # sample once while the first two are running
            await asyncio.sleep(0.15)
            seen_states.append([step.state for step in run.steps])

        watcher = asyncio.create_task(watch())
        await run.shell_group([(f"s{i}", "sleep 0.35") for i in range(3)])
        await watcher

    run = collect(pipeline, max_parallel=2)

    assert seen_states, "the sample should have been taken"
    assert seen_states[0].count("running") == 2
    assert seen_states[0].count("queued") == 1
    assert all(step.state == "done" for step in run.steps)


def test_groups_bundles_steps_by_submission():
    async def pipeline(run: Run):
        await run.sh("first", "true")
        await run.shell_group([("a", "true"), ("b", "true")])

    groups = collect(pipeline).groups()

    assert [len(group) for group in groups] == [1, 2]


def test_skip_records_a_reason_without_running_anything():
    async def pipeline(run: Run):
        run.skip("up", "--no-up")

    step = collect(pipeline).steps[0]

    assert step.state == "skipped"
    assert step.status == "--no-up"
    assert step.ok, "a skipped step is not a failure"
    assert not step.started


def test_elapsed_is_zero_before_start_and_frozen_after_end():
    step = Step("x", 1)
    assert step.elapsed == 0.0

    step.started = time.perf_counter()
    step.ended = step.started + 1.5
    assert step.elapsed == pytest.approx(1.5)


# -- renderers ----------------------------------------------------------------------------


def test_plain_renderer_emits_no_ansi_and_one_line_per_transition(capsys):
    async def pipeline(run: Run):
        await run.sh("ok step", "echo ':: fine'")
        await run.sh("bad step", "exit 2")

    with plain("title") as render:
        asyncio.run(drive(pipeline, render, interval=0.005))

    out = capsys.readouterr().out

    assert "\x1b[" not in out, "plain output must not move the cursor"
    assert out.count("[  ok] ok step") == 1
    assert "[FAIL] bad step - exit 2" in out
    assert "title" in out


def _chosen(manager) -> str:
    """Which @contextmanager-decorated renderer this is."""
    return manager.func.__name__  # type: ignore[attr-defined]


def test_renderer_for_picks_plain_under_pytest():
    """Under pytest stdout is never a terminal, so this is the fallback path for free."""
    assert _chosen(renderer_for("x")) == _chosen(plain("x")) == "plain"

    with renderer_for("", tui=True) as render:
        render(Run())  # must not raise


def test_no_tui_forces_plain():
    assert _chosen(renderer_for("x", tui=False)) == "plain"
