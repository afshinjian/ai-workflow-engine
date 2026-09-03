"""Registry construction, byte-count/digest goldens, and SemVer acceptance tests."""

import hashlib

import pytest
from pydantic import ValidationError

from ai_workflow_engine.models import StrictModel
from ai_workflow_engine.prompt import models as prompt_models
from ai_workflow_engine.prompt.models import PromptStrictModel, PromptTemplate
from ai_workflow_engine.prompt.templates import TEMPLATE_REGISTRY, get_fragments, get_template

# Recomputed for T-307's `## Verification evidence` section and template version 1.0.0 -> 1.1.0.
# Values are explicit literals, computed once from the built registry and hardcoded here --
# never re-derived from `TEMPLATE_REGISTRY` inside a test, which would make the golden vacuous.
GOLDEN: dict[str, tuple[int, str]] = {
    "plan-review": (
        1796,
        "51db4df3a4032995bd64d1184e5f4090294be7376ecff83d3db1f89b335acda5",
    ),
    "implementation": (
        1829,
        "6d1544dfcf3d0bdbc24206e5309f1f6b86b5aefbd51dbc64b426186371570cee",
    ),
    "implementation-review": (
        1809,
        "4d1fad411380d3778216db73f2986c11da05275190145c439b90521b32d847bb",
    ),
    "remediation": (
        1890,
        "0bc2e440c25ba2accc6d37f6920217a2c77a886b510e511044eab9c01710b9b4",
    ),
    "governance-closeout": (
        1825,
        "c3e37ffb4ddb253f46acab6b72433bada3137a3805707b2625f2f66f9d858184",
    ),
    "governance-review": (
        1822,
        "4f28f597fc607466d52f64a8024a2e87a448f40173825883fd1609ddfa59c3a1",
    ),
    "push": (
        2981,
        "c259be0321bf31497faf1c8be2857d1f2f2d3d2043162844184e56102240be98",
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
    assert template.version == "1.1.0"
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
        "engine_provenance",
        "verification_evidence",
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
