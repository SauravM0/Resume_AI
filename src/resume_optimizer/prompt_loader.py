"""Prompt loading helpers for AI-backed phases."""

from __future__ import annotations

from pathlib import Path

from .constants import DEFAULT_PROFILE_ENCODING
from .job_models import RawJobDescriptionRequest
from .phase1_deterministic_models import DeterministicJobDescriptionExtraction
from .phase3_models import Phase3GenerationPayload

PHASE1_JOB_ANALYSIS_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "phase1_job_analysis_prompt.txt"
)
PHASE1_JOB_ENRICHMENT_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "phase1_job_enrichment_prompt.txt"
)
PHASE3_GENERATION_SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "phase3_generation_system_prompt.txt"
)
PHASE5_SUMMARY_GENERATION_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "phase5_summary_generation_prompt.txt"
)
PHASE5_BULLET_REWRITE_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "phase5_bullet_rewrite_prompt.txt"
)
RAW_JOB_DESCRIPTION_PLACEHOLDER = "<<<RAW_JOB_DESCRIPTION>>>"
DETERMINISTIC_EXTRACTION_PLACEHOLDER = "<<<DETERMINISTIC_EXTRACTION_JSON>>>"
PHASE3_GENERATION_PAYLOAD_PLACEHOLDER = "<<<PHASE3_GENERATION_PAYLOAD>>>"


def load_phase1_job_analysis_prompt_template() -> str:
    """Load the Phase 1 job analysis prompt template from disk."""

    try:
        template = PHASE1_JOB_ANALYSIS_PROMPT_PATH.read_text(
            encoding=DEFAULT_PROFILE_ENCODING
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Phase 1 job analysis prompt file not found: {PHASE1_JOB_ANALYSIS_PROMPT_PATH}"
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Unable to read Phase 1 job analysis prompt file: {PHASE1_JOB_ANALYSIS_PROMPT_PATH}"
        ) from exc

    if RAW_JOB_DESCRIPTION_PLACEHOLDER not in template:
        raise ValueError(
            "Phase 1 job analysis prompt template is missing the raw job description placeholder"
        )

    return template


def format_phase1_job_analysis_prompt(request: RawJobDescriptionRequest) -> str:
    """Inject a raw job description into the Phase 1 prompt template."""

    template = load_phase1_job_analysis_prompt_template()
    return template.replace(
        RAW_JOB_DESCRIPTION_PLACEHOLDER,
        request.job_description_text,
        1,
    )


def load_phase1_job_enrichment_prompt_template() -> str:
    """Load the rebuilt Phase 1 enrichment prompt template from disk."""

    try:
        template = PHASE1_JOB_ENRICHMENT_PROMPT_PATH.read_text(
            encoding=DEFAULT_PROFILE_ENCODING
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Phase 1 job enrichment prompt file not found: {PHASE1_JOB_ENRICHMENT_PROMPT_PATH}"
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Unable to read Phase 1 job enrichment prompt file: {PHASE1_JOB_ENRICHMENT_PROMPT_PATH}"
        ) from exc

    if RAW_JOB_DESCRIPTION_PLACEHOLDER not in template:
        raise ValueError(
            "Phase 1 job enrichment prompt template is missing the raw job description placeholder"
        )
    if DETERMINISTIC_EXTRACTION_PLACEHOLDER not in template:
        raise ValueError(
            "Phase 1 job enrichment prompt template is missing the deterministic extraction placeholder"
        )
    return template


def format_phase1_job_enrichment_prompt(
    request: RawJobDescriptionRequest,
    deterministic_extraction: DeterministicJobDescriptionExtraction,
) -> str:
    """Render the rebuilt Phase 1 prompt with raw JD and deterministic artifact."""

    template = load_phase1_job_enrichment_prompt_template()
    rendered = template.replace(
        RAW_JOB_DESCRIPTION_PLACEHOLDER,
        request.job_description_text,
        1,
    )
    return rendered.replace(
        DETERMINISTIC_EXTRACTION_PLACEHOLDER,
        deterministic_extraction.model_dump_json(indent=2, exclude_none=True),
        1,
    )


def load_phase3_generation_system_prompt() -> str:
    """Load the Phase 3 generation system prompt template from disk."""

    try:
        return PHASE3_GENERATION_SYSTEM_PROMPT_PATH.read_text(
            encoding=DEFAULT_PROFILE_ENCODING
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Phase 3 generation system prompt file not found: {PHASE3_GENERATION_SYSTEM_PROMPT_PATH}"
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Unable to read Phase 3 generation system prompt file: {PHASE3_GENERATION_SYSTEM_PROMPT_PATH}"
        ) from exc


def format_phase3_generation_user_prompt(payload: Phase3GenerationPayload) -> str:
    """Render the compact assembled Phase 3 payload into the user prompt body."""

    return (
        "Assembled Phase 3 generation payload:\n"
        f"{payload.model_dump_json(indent=2, exclude_none=True)}"
    )


def load_phase5_summary_generation_prompt() -> str:
    """Load the Phase 5 summary-generation prompt template from disk."""

    try:
        return PHASE5_SUMMARY_GENERATION_PROMPT_PATH.read_text(
            encoding=DEFAULT_PROFILE_ENCODING
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "Phase 5 summary generation prompt file not found: "
            f"{PHASE5_SUMMARY_GENERATION_PROMPT_PATH}"
        ) from exc
    except OSError as exc:
        raise OSError(
            "Unable to read Phase 5 summary generation prompt file: "
            f"{PHASE5_SUMMARY_GENERATION_PROMPT_PATH}"
        ) from exc


def load_phase5_bullet_rewrite_prompt() -> str:
    """Load the Phase 5 bullet-rewrite prompt template from disk."""

    try:
        return PHASE5_BULLET_REWRITE_PROMPT_PATH.read_text(
            encoding=DEFAULT_PROFILE_ENCODING
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "Phase 5 bullet rewrite prompt file not found: "
            f"{PHASE5_BULLET_REWRITE_PROMPT_PATH}"
        ) from exc
    except OSError as exc:
        raise OSError(
            "Unable to read Phase 5 bullet rewrite prompt file: "
            f"{PHASE5_BULLET_REWRITE_PROMPT_PATH}"
        ) from exc
