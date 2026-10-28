from pathlib import Path
import hashlib
import json
import yaml
from .models import FusionPolicy


def policy_hash(policy):
    return hashlib.sha256(
        json.dumps(
            FusionPolicy.model_validate(policy.model_dump(mode="json")).model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def load_policy(path: Path):
    return FusionPolicy.model_validate(yaml.safe_load(path.read_text()))
