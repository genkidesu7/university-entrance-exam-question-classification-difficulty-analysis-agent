# EDU-C2-029 — Unit Tests: every node emits a PROGRESS_UPDATE on entry
#
# agenticstar-deploy requires one non-terminal progress event per stage so the
# caller's UI has something to show. The event is emitted before any input
# validation, so an empty state is enough to reach it.

import importlib

import pytest
from shared.services.events.types import EventType

NODES = [
    ("src.nodes.pre_process_node", "PreProcessNode", "pre_process"),
    ("src.nodes.domain_classify_node", "DomainClassifyNode", "domain_classify"),
    ("src.nodes.bloom_level_node", "BloomLevelNode", "bloom_level"),
    ("src.nodes.difficulty_score_node", "DifficultyScoreNode", "difficulty_score"),
    ("src.nodes.post_process_node", "PostProcessNode", "post_process"),
]


@pytest.mark.parametrize(("module_name", "class_name", "stage"), NODES)
def test_node_emits_progress_update_on_entry(monkeypatch, module_name, class_name, stage):
    module = importlib.import_module(module_name)
    events = []

    class Recorder:
        def emit_event(self, **kwargs):
            events.append(kwargs)

    monkeypatch.setattr(module, "emitter", lambda: Recorder())
    getattr(module, class_name)().execute({})

    assert len(events) == 1
    assert events[0]["event_type"] is EventType.PROGRESS_UPDATE
    assert events[0]["metadata"]["stage"] == stage
    assert events[0]["message"]
