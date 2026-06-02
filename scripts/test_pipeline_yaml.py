"""Validate azure-pipelines.yml structure matches architecture requirements."""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("SKIP: pyyaml not installed")
    sys.exit(0)

ROOT = Path(__file__).parent.parent
PIPELINE = ROOT / "pipelines" / "azure-pipelines.yml"


def load():
    if not PIPELINE.exists():
        return None, "pipeline file not found"
    try:
        return yaml.safe_load(PIPELINE.read_text()), None
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"


def check(condition, message):
    if not condition:
        print(f"FAIL  {message}")
        return False
    print(f"OK    {message}")
    return True


def main():
    doc, err = load()
    passed = True

    passed &= check(doc is not None, f"file parses: {err or 'ok'}")
    if doc is None:
        sys.exit(1)

    stages = {s["stage"]: s for s in doc.get("stages", [])}

    passed &= check("infra" in stages, "infra stage present")
    passed &= check("functions" in stages, "functions stage present")
    passed &= check("frontend" in stages, "frontend stage present")

    # infra stage checks
    if "infra" in stages:
        infra_yaml = str(stages["infra"])
        passed &= check("main.bicep" in infra_yaml, "infra stage references main.bicep")
        passed &= check("az deployment" in infra_yaml, "infra stage runs az deployment")
        passed &= check("apisports-api-key" in infra_yaml, "infra stage provisions apisports secret")
        passed &= check("anthropic-api-key" in infra_yaml, "infra stage provisions anthropic secret")
        passed &= check("cosmos-connection-string" in infra_yaml, "infra stage provisions cosmos secret")

    # functions stage checks
    if "functions" in stages:
        fn_yaml = str(stages["functions"])
        passed &= check("uv" in fn_yaml, "functions stage uses uv")
        passed &= check("functionapp" in fn_yaml.lower(), "functions stage deploys to functionapp")
        passed &= check("infra" in str(stages["functions"].get("dependsOn", "")), "functions depends on infra")

    # frontend stage checks
    if "frontend" in stages:
        fe_yaml = str(stages["frontend"])
        passed &= check("npm" in fe_yaml, "frontend stage uses npm")
        passed &= check("AzureStaticWebApp" in fe_yaml, "frontend stage uses AzureStaticWebApp task")
        passed &= check("VITE_API_BASE_URL" in fe_yaml, "frontend stage injects VITE_API_BASE_URL")

    if passed:
        print("\nAll checks passed.")
    else:
        print("\nSome checks failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
