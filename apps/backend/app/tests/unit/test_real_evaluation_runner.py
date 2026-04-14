from __future__ import annotations

import json
from pathlib import Path

from backend.app.evaluation import (
    EvaluationCaseDefinition,
    EvaluationCaseMetadata,
    EvaluationExpectedOutputs,
    EvaluationPackType,
    EvaluationRunnerConfig,
    LocalFileArtifactStore,
    OrchestratedRealPipelineRunner,
    load_saved_evaluation_run,
    render_loaded_run_summary,
)
from backend.app.orchestration.enums import PipelineStatus, StageName, StageStatus
from backend.app.scripts.run_real_evaluation import main


def test_real_runner_dry_run_writes_manifest_and_stage_artifacts(tmp_path: Path) -> None:
    case = EvaluationCaseDefinition(
        metadata=EvaluationCaseMetadata(
            case_id="case.real_runner.dry_run",
            pack_type=EvaluationPackType.END_TO_END,
            scenario="dry_run_backend_case",
            description="Dry-run coverage for the real runner shell and manifests.",
        ),
        input_payload={
            "source_profile_path": str((Path.cwd() / "data" / "master_profile.example.json").resolve()),
            "job_description_text": "Build reliable Python services and improve APIs.",
            "template_id": "ats_standard",
        },
        expected_outputs=EvaluationExpectedOutputs(
            expected_pipeline_status=PipelineStatus.PENDING,
        ),
    )

    runner = OrchestratedRealPipelineRunner()
    artifact_store = LocalFileArtifactStore(tmp_path)
    result = runner.run_case_with_details(
        case,
        artifact_store=artifact_store,
        config=EvaluationRunnerConfig(
            use_live_llm=False,
            enable_render=False,
            persist_artifacts=True,
            fail_fast=True,
            stop_after="full",
        ),
    )

    assert result.run_manifest.execution_mode == "dry_run"
    assert result.run_manifest.run_status.value == "passed"
    assert result.actual_outputs.pipeline_status == PipelineStatus.PENDING
    assert [stage.stage_name for stage in result.actual_outputs.stage_outputs[:3]] == [
        StageName.LOAD_SOURCE_PROFILE,
        StageName.NORMALIZE_SOURCE_DATA,
        StageName.INGEST_JOB_DESCRIPTION,
    ]
    assert any(stage.status == StageStatus.SKIPPED for stage in result.actual_outputs.stage_outputs)
    assert result.run_summary.artifact_manifest_path is not None
    assert Path(result.run_summary.artifact_manifest_path).exists()
    assert (tmp_path / result.run_manifest.run_id / "run_manifest.json").exists()
    assert (tmp_path / result.run_manifest.run_id / "manifest.json").exists()
    assert (tmp_path / result.run_manifest.run_id / "summary.md").exists()
    assert len(result.artifact_manifest.entries) == 3
    assert all(Path(entry.storage_path).exists() for entry in result.artifact_manifest.entries)
    for entry in result.artifact_manifest.entries:
        document = json.loads(Path(entry.storage_path).read_text(encoding="utf-8"))
        metadata = json.loads(Path(entry.metadata_path).read_text(encoding="utf-8"))
        assert "artifact_metadata" in document
        assert document["artifact_metadata"]["run_id"] == result.run_manifest.run_id
        assert document["artifact_metadata"]["case_id"] == case.metadata.case_id
        assert metadata["run_id"] == result.run_manifest.run_id
        assert metadata["case_id"] == case.metadata.case_id
        assert metadata["stage_name"] == entry.stage_name.value
        assert metadata["schema_version"] == entry.schema_version

    loaded_run = load_saved_evaluation_run(tmp_path / result.run_manifest.run_id)
    rebuilt_summary = render_loaded_run_summary(loaded_run)
    assert loaded_run.run_manifest.run_id == result.run_manifest.run_id
    assert loaded_run.artifact_manifest.case_id == case.metadata.case_id
    assert "Artifact Count" in rebuilt_summary
    assert "load_source_profile" in rebuilt_summary


def test_real_evaluation_cli_reports_missing_live_dependencies(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    case_path = tmp_path / "case.json"
    case_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "case_id": "case.real_runner.missing_key",
                    "pack_type": "end_to_end",
                    "scenario": "missing_key",
                    "description": "Fails clearly when live LLM dependencies are missing.",
                },
                "input_payload": {
                    "source_profile_path": str((Path.cwd() / "data" / "master_profile.example.json").resolve()),
                    "job_description_text": "Build reliable Python services and improve APIs.",
                    "template_id": "ats_standard",
                },
                "expected_outputs": {
                    "expected_pipeline_status": "failed",
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--case-file",
            str(case_path),
            "--use-live-llm",
            "true",
            "--enable-render",
            "false",
            "--stop-after",
            "parse",
            "--output-root",
            str(tmp_path / "outputs"),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["results"][0]["execution_mode"] == "real"
    assert payload["results"][0]["run_status"] == "error"
    assert payload["results"][0]["missing_dependencies"][0]["dependency_name"] == "gemini_api_key"
    assert "Missing GEMINI_API_KEY" in payload["results"][0]["final_message"]


def test_real_evaluation_cli_plain_output_marks_dry_run(
    tmp_path: Path,
    capsys,
) -> None:
    case_path = tmp_path / "case.json"
    case_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "case_id": "case.real_runner.cli_dry_run",
                    "pack_type": "end_to_end",
                    "scenario": "cli_dry_run",
                    "description": "Plain shell output exposes dry-run mode and artifact locations.",
                },
                "input_payload": {
                    "source_profile_path": str((Path.cwd() / "data" / "master_profile.example.json").resolve()),
                    "job_description_text": "Build reliable Python services and improve APIs.",
                    "template_id": "ats_standard",
                },
                "expected_outputs": {
                    "expected_pipeline_status": "pending",
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--case-file",
            str(case_path),
            "--use-live-llm",
            "false",
            "--enable-render",
            "false",
            "--output-root",
            str(tmp_path / "outputs"),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "mode=dry_run" in captured.out
    assert "artifact_manifest=" in captured.out


def test_local_artifact_store_redacts_sensitive_values_and_writes_stable_metadata(
    tmp_path: Path,
) -> None:
    store = LocalFileArtifactStore(tmp_path)
    entry = store.persist_stage_artifact(
        run_id="eval.case.redaction.123",
        case_id="case.redaction",
        stage_name=StageName.INGEST_JOB_DESCRIPTION,
        artifact_name="raw_job_description.json",
        payload={
            "job_description_text": "Contact alice@example.com or +1 (555) 123-4567.",
            "api_key": "sk-secret-value",
        },
        content_type="application/json",
    )
    manifest = store.build_manifest(run_id="eval.case.redaction.123", case_id="case.redaction")
    manifest_path = store.write_manifest(manifest)

    assert manifest_path.name == "manifest.json"
    assert entry.relative_path == "stages/ingest_job_description/raw_job_description.json"
    assert Path(entry.metadata_path).name == "raw_job_description.json.metadata.json"

    document = json.loads(Path(entry.storage_path).read_text(encoding="utf-8"))
    metadata = json.loads(Path(entry.metadata_path).read_text(encoding="utf-8"))

    assert document["payload"]["job_description_text"] == "Contact [REDACTED_EMAIL] or [REDACTED_PHONE]."
    assert document["payload"]["api_key"] == "[REDACTED]"
    assert metadata["redacted"] is True
    assert metadata["payload_format"] == "json"
