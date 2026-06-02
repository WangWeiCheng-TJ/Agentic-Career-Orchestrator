import json
import os
import sys
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)
sys.path.append(project_root)

from schemas_definitions import SKILL_SCHEMA, GAP_EFFORT_SCHEMA, ADVISOR_SCHEMA, EDITOR_SCHEMA


class PromptFactory:
    MODE_TO_SCHEMA = {
        "SKILL": SKILL_SCHEMA,
        "GAP_EFFORT": GAP_EFFORT_SCHEMA,
        "ADVISOR": ADVISOR_SCHEMA,
    }

    MODE_TO_EXAMPLE_KEY = {
        "SKILL": "skill",
        "GAP_EFFORT": "gap_effort",
        "ADVISOR": "advisor",
    }

    def __init__(self, root_dir=None):
        self.root = root_dir if root_dir else project_root
        self.template_dir = os.path.join(self.root, "character_setting")
        self.config_path = os.path.join(self.root, "character_setting", "personas.json")

        if not os.path.exists(self.template_dir):
            raise FileNotFoundError(f"Templates dir not found: {self.template_dir}")
        self.env = Environment(loader=FileSystemLoader(self.template_dir), trim_blocks=True, lstrip_blocks=True)

        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.personas = json.load(f)

    def _schema_for_mode(self, mode: str) -> str:
        if mode not in self.MODE_TO_SCHEMA:
            raise ValueError(f"Invalid mode: {mode}")
        return self.MODE_TO_SCHEMA[mode]

    def _active_examples_for_mode(self, expert_config: Dict[str, Any], mode: str) -> List[Dict[str, Any]]:
        example_key = self.MODE_TO_EXAMPLE_KEY.get(mode)
        return expert_config.get("few_shot_examples", {}).get(example_key, [])

    def create_expert_prompt(self, expert_id: str, mode: str, context_data: dict) -> str:
        expert_config = self.personas.get(expert_id)
        if not expert_config:
            raise ValueError(f"Expert ID '{expert_id}' not found in personas.json")

        render_vars = {
            **expert_config,
            **context_data,
            "mode": mode,
            "output_schema": self._schema_for_mode(mode),
            "active_examples": self._active_examples_for_mode(expert_config, mode),
        }

        try:
            template = self.env.get_template("member_prompt.md.j2")
            return template.render(render_vars)
        except Exception as e:
            raise RuntimeError(f"Failed to render expert template: {e}")

    def create_editor_prompt(self, council_opinions: list, context_data: dict) -> str:
        editor_config = getattr(self, "personas", {}).get("EDITOR")
        if not editor_config:
            editor_config = {
                "role_name": "Editor-in-Chief",
                "role_icon": "✍️",
                "focus_area": "Synthesis, Conflict Resolution & Final Polish",
                "philosophy": "I am the decision maker. I filter noise, resolve conflicts between experts, and produce a coherent strategic narrative.",
            }

        render_vars = {
            **editor_config,
            **context_data,
            "council_opinions": council_opinions,
            "editor_schema": EDITOR_SCHEMA,
            "active_examples": editor_config.get("few_shot_examples", {}).get("synthesis", []),
        }

        try:
            template = self.env.get_template("editor_prompt.md.j2")
            return template.render(render_vars)
        except Exception as e:
            raise RuntimeError(f"Failed to render editor template: {e}")