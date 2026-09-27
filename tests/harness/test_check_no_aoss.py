"""The AOSS guard must catch every way AOSS can sneak in, and must not cry wolf on clean infra."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import check_no_aoss  # noqa: E402

AOSS_TYPE = "AWS::" + "OpenSearch" + "Serverless" + "::Collection"


def _write_template(root: Path, resources: dict) -> None:
    out = root / "cdk.out"
    out.mkdir()
    (out / "CluckTalkStack.template.json").write_text(json.dumps({"Resources": resources}), encoding="utf-8")


def test_clean_template_passes(tmp_path):
    _write_template(tmp_path, {"Table": {"Type": "AWS::DynamoDB::Table"}})
    assert check_no_aoss.main(["--root", str(tmp_path)]) == 0


def test_aoss_resource_in_synth_output_fails(tmp_path):
    _write_template(tmp_path, {"Vectors": {"Type": AOSS_TYPE}})
    assert check_no_aoss.main(["--root", str(tmp_path)]) == 1


def test_aoss_cdk_import_in_infra_source_fails(tmp_path):
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "stack.py").write_text(
        "from aws_cdk import aws_opensearch" + "serverless as aoss\n", encoding="utf-8"
    )
    assert check_no_aoss.main(["--root", str(tmp_path)]) == 1


def test_aoss_iam_action_fails(tmp_path):
    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "policy.json").write_text('{"Action": ["' + "aoss" + ':APIAccessAll"]}', encoding="utf-8")
    assert check_no_aoss.main(["--root", str(tmp_path)]) == 1


def test_bedrock_kb_aoss_storage_type_fails(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "kb.py").write_text('storage_type = "OPENSEARCH_' + 'SERVERLESS"\n', encoding="utf-8")
    assert check_no_aoss.main(["--root", str(tmp_path)]) == 1


def test_unparseable_template_is_reported_not_ignored(tmp_path):
    (tmp_path / "cdk.out").mkdir()
    (tmp_path / "cdk.out" / "Broken.template.json").write_text("{not json", encoding="utf-8")
    assert check_no_aoss.main(["--root", str(tmp_path)]) == 2
