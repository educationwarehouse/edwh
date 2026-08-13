import textwrap
from contextlib import chdir

from ewok import Context, task
from ewok.cli import include_other_project_tasks
from invoke import Collection


def test_project_tasks_override_existing_namespace(tmp_path, capsys):
    """A project *.tasks.py must replace a same-named packaged namespace."""

    @task
    def packaged_run(_: Context):
        return "packaged"

    root = Collection("root")
    packaged = Collection("namespace_override")
    packaged.add_task(packaged_run, "run")
    root.add_collection(packaged, "namespace_override")

    project_module = textwrap.dedent(
        """
        from ewok import task

        @task(name="run")
        def project_run(c):
            return "project"
        """
    )

    (tmp_path / "namespace_override.tasks.py").write_text(project_module)

    with chdir(tmp_path):
        include_other_project_tasks(root)

    resolved = root.collections["namespace-override"].tasks["run"]
    assert resolved.body.__name__ == "project_run"
    assert "namespace-override" in capsys.readouterr().err
