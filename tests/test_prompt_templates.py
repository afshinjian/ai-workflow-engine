"""Registry construction, byte-count/digest goldens, and SemVer acceptance tests."""

import hashlib

import pytest
from pydantic import ValidationError

from ai_workflow_engine.models import StrictModel
from ai_workflow_engine.prompt import models as prompt_models
from ai_workflow_engine.prompt.models import PromptStrictModel, PromptTemplate
from ai_workflow_engine.prompt.templates import TEMPLATE_REGISTRY, get_fragments, get_template

GOLDEN: dict[str, tuple[int, str]] = {
    "plan-review": (
        1739,
        "27dde6b824ec24aef65736fb8e66a90985f73bce04323e4957122faf7963008a",
    ),
    "implementation": (
        1772,
        "4aae483d3402332a26bab1ba813d6d7084c9da273702749d8911490198f6bea3",
    ),
    "implementation-review": (
        1752,
        "3417515b3001ae3d105b9e18cfda1892e2fa0774d14345d1f8e55be09d89a575",
    ),
    "remediation": (
        1833,
        "135e61a751b226dff796e143cf17cf5143c3f48e0e0ad374d5534d491a73e2d8",
    ),
    "governance-closeout": (
        1768,
        "9d0ab6e86cc26e555eaaa60493827ef33a27931c5360485424523a354b12f247",
    ),
    "governance-review": (
        1765,
        "7dbd4ace9b1f1af39808a542f4ba90a17abe5e7ce418ebf52034ac712a520cce",
    ),
    "push": (
        2924,
        "e175957cf5939c01fb10381ef04df410c830daa285df8f23757d929b1ea5ec84",
    ),
}


def test_registry_has_exactly_seven_entries() -> None:
    assert set(TEMPLATE_REGISTRY) == set(GOLDEN)
    assert len(TEMPLATE_REGISTRY) == 7


@pytest.mark.parametrize("stage", sorted(GOLDEN))
def test_registry_entry_matches_golden_bytes_and_digest(stage: str) -> None:
    template = get_template(stage)  # type: ignore[arg-type]
    expected_bytes, expected_sha256 = GOLDEN[stage]
    content_bytes = template.content.encode("utf-8")
    assert len(content_bytes) == expected_bytes
    assert template.sha256 == expected_sha256
    assert hashlib.sha256(content_bytes).hexdigest() == expected_sha256
    assert template.version == "1.0.0"
    assert template.stage == stage


def test_unknown_stage_lookup_fails() -> None:
    with pytest.raises(ValueError, match="No registered prompt template"):
        get_template("not-a-stage")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="No registered prompt fragments"):
        get_fragments("not-a-stage")  # type: ignore[arg-type]


def test_content_is_nfc_lf_single_final_newline() -> None:
    import unicodedata

    for stage in GOLDEN:
        content = get_template(stage).content  # type: ignore[arg-type]
        assert unicodedata.normalize("NFC", content) == content
        assert "\r" not in content
        assert content.endswith("\n")
        assert not content.endswith("\n\n")


@pytest.mark.parametrize(
    "version",
    [
        "1.0.0",
        "0.0.0",
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-0.3.7",
        "1.0.0-x-y-z.--",
        "1.0.0-alpha+001",
        "1.0.0+20130313144700",
        "1.0.0-beta+exp.sha.5114f85",
        "1.0.0+21AF26D3---117B344092BD",
    ],
)
def test_accepted_semver_examples(version: str) -> None:
    template = PromptTemplate(
        stage="plan-review",
        version=version,
        content="x\n",
        sha256=hashlib.sha256(b"x\n").hexdigest(),
    )
    assert template.version == version


@pytest.mark.parametrize(
    "version",
    [
        "v1.0.0",
        " 1.0.0",
        "1.0.0 ",
        "1.0.0-",
        "1.0.0-.",
        "1.0.0+",
        "01.0.0",
        "1.01.0",
        "1.0.01",
        "1.0.0-01",
        "1.0.0-01.foo",
        "1.0",
        "1",
        "1.0.0-\u03b1",  # non-ASCII prerelease identifier
        "1.0.0+\u03b1",  # non-ASCII build identifier
    ],
)
def test_rejected_semver_examples(version: str) -> None:
    with pytest.raises(ValidationError):
        PromptTemplate(
            stage="plan-review",
            version=version,
            content="x\n",
            sha256=hashlib.sha256(b"x\n").hexdigest(),
        )


def test_prerelease_and_build_spelling_is_case_sensitive_and_preserved() -> None:
    template = PromptTemplate(
        stage="plan-review",
        version="1.0.0-Alpha.Beta+Build.META",
        content="x\n",
        sha256=hashlib.sha256(b"x\n").hexdigest(),
    )
    assert template.version == "1.0.0-Alpha.Beta+Build.META"


def test_sha256_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PromptTemplate(
            stage="plan-review",
            version="1.0.0",
            content="x\n",
            sha256="0" * 64,
        )


# --- Every prompt model: StrictModel inheritance, closed schema, exact-type fields --


_ALL_PROMPT_MODEL_CLASSES: tuple[type, ...] = (
    prompt_models.PromptTemplate,
    prompt_models.CanonicalGitStatus,
    prompt_models.CanonicalTaskRecord,
    prompt_models.CanonicalTaskSnapshot,
    prompt_models.CanonicalFinding,
    prompt_models.CanonicalCheckResult,
    prompt_models.CanonicalProjectSettings,
    prompt_models.CanonicalFactRule,
    prompt_models.CanonicalGovernanceSettings,
    prompt_models.CanonicalHandoverSettings,
    prompt_models.CanonicalProtectedPathsSettings,
    prompt_models.CanonicalWorkflowSettings,
    prompt_models.CanonicalEngineConfig,
    prompt_models.PromptContext,
    prompt_models.PromptMetadata,
    prompt_models.RenderedPrompt,
    prompt_models.StoredPromptPaths,
    prompt_models.PromptSuccess,
)


@pytest.mark.parametrize("model_class", _ALL_PROMPT_MODEL_CLASSES, ids=lambda c: c.__name__)
def test_every_prompt_model_subclasses_strict_model_via_prompt_strict_model(
    model_class: type,
) -> None:
    assert issubclass(model_class, PromptStrictModel)
    assert issubclass(model_class, StrictModel)
    assert model_class is not StrictModel


@pytest.mark.parametrize("model_class", _ALL_PROMPT_MODEL_CLASSES, ids=lambda c: c.__name__)
def test_every_prompt_model_forbids_extra_fields_and_is_strict(model_class: type) -> None:
    assert model_class.model_config.get("extra") == "forbid"
    assert model_class.model_config.get("strict") is True


def test_prompt_metadata_model_fields_is_exactly_the_closed_field_set() -> None:
    assert set(prompt_models.PromptMetadata.model_fields) == {
        "schema_version",
        "prompt_id",
        "project_id",
        "task_id",
        "stage",
        "template_version",
        "template_sha256",
        "repository_head",
        "allowed_paths",
        "remediation_findings",
        "payload_sha256",
        "markdown_sha256",
        "payload",
    }


def test_prompt_template_rejects_an_unknown_field() -> None:
    with pytest.raises(ValidationError):
        PromptTemplate(
            stage="plan-review",
            version="1.0.0",
            content="x\n",
            sha256=hashlib.sha256(b"x\n").hexdigest(),
            unexpected_field="x",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stage", 1),
        ("stage", None),
        ("version", 1),
        ("content", 1),
        ("sha256", 1),
    ],
)
def test_prompt_template_rejects_wrong_type(field: str, value: object) -> None:
    kwargs = {
        "stage": "plan-review",
        "version": "1.0.0",
        "content": "x\n",
        "sha256": hashlib.sha256(b"x\n").hexdigest(),
        field: value,
    }
    with pytest.raises(ValidationError):
        PromptTemplate(**kwargs)


def test_content_must_end_with_exactly_one_final_newline() -> None:
    with pytest.raises(ValidationError):
        PromptTemplate(
            stage="plan-review",
            version="1.0.0",
            content="x",
            sha256=hashlib.sha256(b"x").hexdigest(),
        )
    with pytest.raises(ValidationError):
        PromptTemplate(
            stage="plan-review",
            version="1.0.0",
            content="x\n\n",
            sha256=hashlib.sha256(b"x\n\n").hexdigest(),
        )
