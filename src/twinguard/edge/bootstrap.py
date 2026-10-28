import json
from .contracts import SourceRegistration
from .storage import engine, put, get
from .worker import ROOT
from twinguard.fusion.models import FusionState


def initialize():
    with engine().begin() as c:
        for value in json.loads((ROOT / "configs/edge/simulation-sources.json").read_text()):
            source = SourceRegistration.model_validate(value)
            if not get(c, "source", source.source_id):
                put(c, "source", source.source_id, source.model_dump(mode="json"))
        if not get(c, "checkpoint", "F1"):
            put(c, "checkpoint", "F1", FusionState().model_dump(mode="json"))
        assets = json.loads((ROOT / "configs/edge/assets.json").read_text())
        for value in assets:
            put(c, "asset", value["asset_id"], value, value["asset_id"])


if __name__ == "__main__":
    initialize()
