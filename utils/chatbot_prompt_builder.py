# utils/chatbot_prompt_builder.py

import json
import re

from pathlib import Path
from string import Template
from typing import Optional, Union

from utils.config import Config
from utils.logging import get_logger

class ChatbotPromptBuilder:
    _instance = None
    _initialized = False

    MODE_APP = "app"
    MODE_TECHNICAL = "technical"
    MODE_PERSONA = "persona"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._prompts = {}
        return cls._instance

    def __init__(self):
        if not self.__class__._initialized:
            self.config = Config()
            self.debug = self.config.get("hr-demo", "debug").lower() == "true"
            self.app_logger = get_logger(self.config.get("log", "app"))
            self.bot_name = self.config.get("chatbot", "name")
            self.app_name = self.config.get("hr-demo", "name")

            self.mode = ChatbotPromptBuilder.MODE_APP
            self._loaded_profiles = {}

            self.__class__._initialized = True

    @classmethod
    def is_request_for_app_info(cls, mode: str) -> bool:
        return mode == cls.MODE_APP

    @classmethod
    def is_request_for_tech_info(cls, mode: str) -> bool:
        return mode == cls.MODE_TECHNICAL

    @classmethod
    def is_request_for_chatbot_convo(cls, mode: str) -> bool:
        return mode == cls.MODE_PERSONA

    def infer_mode_from_input(self, input: str) -> str:
        input_lower = input.lower()
        words = set(re.findall(r'\w+', input_lower))

        app_specific_keywords = {
            "advisor", "alarie", "aligning", "alignment", "america", "american", "app",
            "china", "chinese", "demo", "developer", "developers", "document", "documents",
            "documentation", "endpoint", "engineer", "engineers", "german", "germany",
            "globaltech", "member", "members", "motivation", "ontologyone", "ontologyone's",
            "project", "role", "roles", "singapore", "team", "timeline", "unified", "unifying",
            "us", "usa", "version"
        }

        app_related_phrases = {"full stack", "the states", "use case"}

        technical_keywords = {
            "advantage", "advantages", "ai", "api", "architecture", "backend", "chatbot",
            "cloud", "code", "database", "databases", "diagram", "diagrams", "disadvantage",
            "disadvantages", "embedding", "embeddings", "fastapi", "framework", "frontend",
            "graph", "image", "images", "inference", "knowledge", "language", "languages",
            "layer", "layers", "llm", "markdown", "model", "models", "ontology", "ontologies",
            "openai", "owl", "pic", "picture", "pictures", "prompt", "python", "quadstore",
            "query", "rag", "rdf", "rdfs", "react", "reasoning", "semantic", "shacl", "sparql",
            "store", "system", "swrl", "tech", "technical", "technology", "technologies",
            "token", "tools", "triplestore", "turtle", "ui", "ux", "vector"
        }

        mode = ChatbotPromptBuilder.MODE_PERSONA
        if words & app_specific_keywords or any(phrase in input_lower for phrase in app_related_phrases):
            mode = ChatbotPromptBuilder.MODE_APP
        elif words & technical_keywords:
            mode = ChatbotPromptBuilder.MODE_TECHNICAL

        if self.debug:
            print(f"{self.__class__.__name__} infer_mode mode = {mode}")

        return mode

    def get_mode(self):
        return self.mode
    
    def get_profile(self, chat_mode) -> str:
        if chat_mode != self.mode:
            self.mode = chat_mode

        if chat_mode == self.MODE_APP:
            prompt = self.build_app_prompt()
        elif chat_mode == self.MODE_TECHNICAL:
            prompt = self.build_technical_prompt()
        elif chat_mode == self.MODE_PERSONA:
            prompt = self.build_persona_prompt()
        else:
            raise ValueError(f"Unknown mode: {chat_mode}")

        return f"### Assistant_Profile\n{prompt}"

    def get_user_prompt(self, user_message: str, doc_context: str, story_context: str, image_context, chat_history_context: str) -> str:
        context_list = []
        if image_context:
            context_list.append(f"### Diagram_Context\n{image_context}")
        if doc_context:
            context_list.append(f"### Document_Context\n{doc_context}")
        if story_context:
            context_list.append(f"### Story_Context\n{story_context}")
        if chat_history_context:
            context_list.append(f"### Conversation_History\n{chat_history_context}")

        context_list.append(f"### Current_User_Question\n{user_message}")
        return "\n\n".join(context_list)

    def _smart_join(self, items, prefix="- ", sep=", ", last_sep="and"):
        if isinstance(items, dict):
            return "\n".join(f"{prefix}{k}{sep}{v}" for k, v in items.items())
        if isinstance(items, (list, set)):
            items = sorted(items) if isinstance(items, set) else items
            if len(items) == 0:
                return ""
            if len(items) == 1:
                return items[0]
            return f"{sep.join(items[:-1])} {last_sep} {items[-1]}"
        if isinstance(items, str):
            return items
        return str(items)

    def _get_profile_for_mode(self, mode: str) -> Optional[dict]:
        if mode in self._loaded_profiles:
            return self._loaded_profiles[mode]

        profile_path_str = self.config.get("chatbot", "profile_path")
        file_names = self.config.get("chatbot", f"load_{mode}_profile").split(",")
        base_dir = Path(__file__).parent
        profile_dir = (base_dir / profile_path_str).resolve()

        merged = {}
        for fname in map(str.strip, file_names):
            path = profile_dir / fname
            if not path.exists():
                self.app_logger.error(f"Missing profile: {path}")
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    template = Template(f.read())
                    content = template.substitute(app_name=self.app_name, bot_name=self.bot_name)
                    merged.update(json.loads(content))
            except Exception as e:
                self.app_logger.error(f"Error loading profile {path}: {e}")

        self._loaded_profiles[mode] = merged
        return merged
    
    def _format_block(self, items: Union[list, set, str], prefix: str = "- ") -> str:
        if not items:
            return "(none)"

        if isinstance(items, str):
            return f"{prefix}{items}"

        if isinstance(items, set):
            items = sorted(items)  # for consistent output

        return "\n".join(f"{prefix}{item}" for item in items)

    def _build_section(self, items, prefix:str = "- ") -> str:
        return self._format_block(items, prefix)

    # load chatbot's essence - common to all modes
    def build_chatbot_core(self, mode:str, profile:dict) -> str:
        bot_name = profile.get('name')
        bot_role = profile.get('role')
        bot_office = profile.get('office')
        bot_gender = profile.get('gender')
        bot_notes = self._build_section(profile.get("notes"))

        app = profile.get("app")
        app_name = app.get('name')
        app_description = app.get('description')
        app_access = app.get('location')

        responsibility = ""
        if mode == ChatbotPromptBuilder.MODE_APP:
          responsibility += f"You are responding to user queries relating to {app_name} in a {profile.get('profile_type')} capacity."
        if mode == ChatbotPromptBuilder.MODE_TECHNICAL:
          responsibility += f"You are sharing your technical know-how with the user in a {profile.get('profile_type')} capacity."
        if mode == ChatbotPromptBuilder.MODE_PERSONA:
          responsibility += f"However, you are taking a break to engage in light banter with the user in a {profile.get('profile_type')} way."

        members = profile.get("dev_team").get("members")
        team = ", ".join(f"{member.get('name')} ({member.get('role')})" for member in members) if members else "(none)"

        return f"""You are {bot_name}, {bot_role}.
{app_name} is a {app_description}. User can try the app by {app_access}. Fellow team members are: {team}. {responsibility}
You work {bot_office}; when ask for gender and age, you {bot_gender}.
Notes: 
{bot_notes}"""

    def _build_response_logic(self, profile:dict) -> str:
        knowledge_scope = profile.get('knowledge_scope')
        assumed_user_knowledge = profile.get('assumed_user_knowledge', "")

        behavior = profile.get("behavior", "")
        opinion_policy = profile.get("opinion_policy", "")
        off_topic = profile.get("off_topic", "")

        prompt = f"{knowledge_scope}. "
        if assumed_user_knowledge:
            prompt += f"When responding to queries, you assume the user has {assumed_user_knowledge}. "

        if behavior or opinion_policy or off_topic:
            prompt += "\nYour responses are:\n"
            if behavior:
                prompt += f"{self._build_section(behavior)}"
            if opinion_policy:
                if behavior:
                    prompt += "\n"
                prompt += f"{self._build_section(opinion_policy)}"
            if off_topic:
                if behavior or opinion_policy:
                    prompt += "\n"
                prompt += f"{self._build_section(off_topic)}"

        return prompt

    def _build_response_format(self, profile:dict) -> str:          
        response_style = profile.get("style")
        length_limit = profile.get("length_limit")
        formatting = profile.get("formatting")

        return f"""Your replies are {response_style}. You respond using a {length_limit}. You:
{self._build_section(formatting)}. """

    def _build_style_guide(self, profile:dict) -> str:
        writing = profile.get("writing")
        writing_format = writing.get("format")
        writing_preferences = self._smart_join(writing.get("preferences"))

        return f"Your writing style is {writing_format}. You use {writing_preferences}."

    # specifies the operational guardrails
    def _build_operational_boundaries(self, profile:dict) -> str:
        safety_and_ethics = profile.get("safety_and_ethics")
        sae_bias_avoidance = self._build_section(safety_and_ethics.get("bias_avoidance"))
        sae_language = self._build_section(safety_and_ethics.get("language"))

        project_caveats = profile.get("project_caveats")
        app_and_chatbot_status = self._build_section(project_caveats.get("app_and_chatbot_status"))

        diagram_status = project_caveats.get("diagram_status")
        diagram_status = "; ".join(f"{key} ({value})" for key, value in diagram_status.items())
        diagram_status =self._build_section(f"not all ontology diagrams are available. Availability of ontology diagrams: {diagram_status}")

        access = profile.get("access")
        access_to_ontology_data = self._build_section(access.get("ontology_data"))
        access_to_graph_interactions = self._build_section(access.get("graph_interactions"))

        escalation = self._build_section(profile.get("escalation").get("method"))

        return f"""{sae_bias_avoidance}
{sae_language}
{app_and_chatbot_status}
{diagram_status}
{access_to_ontology_data}
{access_to_graph_interactions}
{escalation}"""

    # specifies the narratives that the chatbot can share with the user
    # chatbot is generally allowed to make up interactions with E.V. Alarie but not real team members
    def _build_narrative_boundaries(self, profile:dict) -> str:
        return self._build_section(profile)

    def build_app_prompt(self) -> str:
      return self._build_app_technical_prompt(ChatbotPromptBuilder.MODE_APP)

    def build_technical_prompt(self) -> str:
      return self._build_app_technical_prompt(ChatbotPromptBuilder.MODE_TECHNICAL)

    def _build_app_technical_prompt(self, mode:str) -> str:
        profile = self._get_profile_for_mode(mode)

        chatbot_core = self.build_chatbot_core(mode, profile)

        personality = profile.get("personality")
        style_guide = profile.get("style_guide")
        tone = self._build_section(personality.get("tone"))
        engagement_style = self._build_section(style_guide.get('engagement'))

        quirks = self._build_section(personality.get("quirks"))
        likes = self._build_section(personality.get("likes"))
        dislikes = self._build_section(personality.get("dislikes"))

        response_logic_query = profile.get("response_logic").get(f"{mode}_queries")
        response_logic = self._build_response_logic(response_logic_query)

        response_format = self._build_response_format(profile.get("response_format"))
        style_guide = self._build_style_guide(style_guide)

        operational_boundaries = self._build_operational_boundaries(profile.get("boundaries"))
        narrative_boundaries = self._build_narrative_boundaries(profile.get("boundaries").get("narratives"))
            
        return f"""{chatbot_core}

Tone and demeanor:
{tone}
{engagement_style}

You may reflect the following traits if relevant:
{quirks}
{likes}

Do not express or imply the following:
{dislikes}

{response_logic}

{response_format}
{style_guide}

Operational boundaries to observe:
{operational_boundaries}

Narrative boundaries to observe:
{narrative_boundaries}"""

    def build_personal_information(self, profile:dict) -> str:
        appearance = ""
        for key, value in profile.get("appearance").items():
            appearance += f"- {key}: {value}\n"

        fave = profile.get("favorites")
        fave_colors = self._build_section(f"colors: {self._smart_join(fave.get('colors'))}")
        fave_foods = self._smart_join(fave.get("fruits") + fave.get("beverages") + fave.get("foods"))
        fave_foods = self._build_section(f"food: {fave_foods}")

        interests = profile.get("interests")
        science = self._build_section(self._smart_join(interests.get("science")))
        sports = self._build_section(f"{self._smart_join(interests.get('sports'))}")
        hobbies = self._build_section(f"hobbies: {self._smart_join(interests.get('hobbies'))}")

        return f"""
What you look like:
{appearance}
Your birthday: {profile.get("birthday")}
Relationship status: {profile.get("relationship_status")}
Home: {profile.get("home")}
Living arrangement: {profile.get("lives_with")}

What you like:
{fave_colors}
{fave_foods}

Your interests and hobbies:
{science}
{sports}
{hobbies}"""

    def build_persona_prompt(self) -> str:
        mode = ChatbotPromptBuilder.MODE_PERSONA
        profile = self._get_profile_for_mode(mode)

        chatbot_core = self.build_chatbot_core(mode, profile)
        personal_information = self.build_personal_information(profile)

        style_guide = profile.get("style_guide")
        engagement_style = self._build_section(style_guide.get('engagement'))

        personality = profile.get("personality")
        tone = self._build_section(personality.get("tone"))
        quirks = self._build_section(personality.get("quirks"))
        likes = self._build_section(personality.get("likes"))
        dislikes = self._build_section(personality.get("dislikes"))

        response_logic = profile.get("response_logic")
        response_logic = self._build_response_logic(response_logic)

        response_format = self._build_response_format(profile.get("response_format"))
        style_guide = self._build_style_guide(style_guide)

        operational_boundaries = self._build_operational_boundaries(profile.get("boundaries"))
        narrative_boundaries = self._build_narrative_boundaries(profile.get("boundaries").get("narratives"))

        return f"""{chatbot_core}
{personal_information}

Tone and demeanor:
{tone}
{engagement_style}

You may exhibit the following personality traits:
{quirks}

You like:
{likes}

You tend to avoid:
{dislikes}

{response_logic}

{response_format}{style_guide}

Operational boundaries to observe:
{operational_boundaries}

Narrative boundaries to observe:
{narrative_boundaries}"""