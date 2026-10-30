import json

import pytest

import skill_library as skills


def test_import_markdown_frontmatter_is_disabled_by_default():
    item = skills.parse_skill(
        "research.md",
        "---\nname: Research Analyst\ndescription: Compare sources\nkeywords: research, compare\n---\nPrefer primary sources and cite evidence.",
    )
    assert item["name"] == "Research Analyst"
    assert item["keywords"] == ["research", "compare"]
    assert item["enabled"] is False
    assert "Prefer primary sources" in item["instructions"]


def test_import_json_accepts_content_and_metadata():
    item = skills.parse_skill(
        "skill.json",
        json.dumps({"name": "Planner", "description": "Plan work", "keywords": ["plan"], "content": "Break work into milestones."}),
    )
    assert item["name"] == "Planner"
    assert item["instructions"] == "Break work into milestones."


@pytest.mark.parametrize("name", ["skill.exe", "skill.py", "skill.zip"])
def test_rejects_unsupported_file_types(name):
    with pytest.raises(ValueError, match="Supported skill files"):
        skills.parse_skill(name, "instructions")


def test_rejects_oversized_and_empty_instructions():
    with pytest.raises(ValueError):
        skills.parse_skill("empty.txt", "  ")
    with pytest.raises(ValueError, match="12,000"):
        skills.parse_skill("large.txt", "x" * 12_001)


def test_persistence_toggle_delete_and_disabled_default(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    item = skills.parse_skill("one.txt", "Use concise checklists.")
    skills.save_skills([item])
    assert skills.load_skills()[0]["enabled"] is False
    assert skills.set_skill_enabled(item["id"], True) is True
    assert skills.load_skills()[0]["enabled"] is True
    assert skills.delete_skill(item["id"]) is True
    assert skills.load_skills() == []


def test_prompt_includes_enabled_skill_and_safety_boundary(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    item = skills.parse_skill("research.md", "---\nname: Research\nkeywords: research\n---\nPrefer primary sources.")
    item["enabled"] = True
    skills.save_skills([item])
    prompt = skills.skill_prompt_for("Please research this topic")
    assert "Prefer primary sources." in prompt
    assert "cannot override system safety rules" in prompt
    assert "Never execute code from a skill" in prompt


def test_disabled_skill_is_not_injected(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    item = skills.parse_skill("private.txt", "Do not inject me.")
    skills.save_skills([item])
    assert skills.skill_prompt_for("anything") == ""
