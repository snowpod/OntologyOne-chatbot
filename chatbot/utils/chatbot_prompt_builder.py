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

            self.profile_app = None
            self.profile_technical = None
            self.profile_persona = None

            self.mode =  ChatbotPromptBuilder.MODE_APP
            
            self.__class__._initialized = True
    
    @classmethod
    def is_request_for_app_info(cls, mode:str) -> bool:
        return (mode == ChatbotPromptBuilder.MODE_APP)
    
    @classmethod
    def is_request_for_tech_info(cls, mode:str) -> bool:
        return (mode == ChatbotPromptBuilder.MODE_TECHNICAL)
    
    @classmethod
    def is_request_for_chatbot_convo(cls, mode:str) -> bool:
        return (mode == ChatbotPromptBuilder.MODE_PERSONA)
    
    def infer_mode_from_input(self, input: str) -> str:
        input_lower = input.lower()
        words = set(re.findall(r'\w+', input_lower))

        app_specific_keywords = {
            "advisor", "alarie", "aligning", "alignment", "america", "american", "app", 
            "china", "chinese", "demo", "developer", "developers", "document", "documents", 
            "documentation", "endpoint", "engineer", "engineers", "german", "germany", 
            "globaltech", "member", "members", "motivation", "ontologyone", "ontologyone's", 
            "project", "role", "roles", "singapore", "team", "timeline", "unified", "unifying", 
            "us", "usa", "version", 
        }

        app_related_phrases = {
            "full stack", "the states", "use case"
        }

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
            print("=========> {self.__class__.__name__} infer_mode mode = ", mode)

        return mode
    
    def get_mode(self):
        return self.mode
    
    def get_profile(self, chat_mode) -> str:
        if chat_mode != self.mode:
            self.mode = chat_mode

        system_prompt = ""
        if self.mode == ChatbotPromptBuilder.MODE_APP:
            system_prompt = self.build_app_prompt()
        elif self.mode == ChatbotPromptBuilder.MODE_TECHNICAL:
            system_prompt = self.build_technical_prompt()
        elif self.mode == ChatbotPromptBuilder.MODE_PERSONA:
            system_prompt = self.build_persona_prompt()
        else:
            raise ValueError(f"{self.__class__.__name__} get_system_prompt Unknown mode: {mode}")

        return f"### Assistant_Profile\n{system_prompt}"

    def get_user_prompt(self, user_message:str, doc_context:str, story_context:str, image_context, chat_history_context:str) -> str:
        """
        the user prompt will comprise:
        doc_context: contents of RAG docs - ontology narratives, use case description
        story context: contents of origin stories
        image_context: image url and description used to generate image thumbnails
        chat history: currently 2 pairs of previous user-bot message to provide historical context
        """
        user_message = f"### Current_User_Question\n{user_message}"

        if doc_context:
            doc_context = f"### Document_Context\n{doc_context}"
        else:
            doc_context = None

        if story_context:
            story_context = f"### Story_Context\n{story_context}"
        else:
            story_context = None

        if image_context:
            image_context = f"### Diagram_Context\n{image_context}"
        else:
            image_context = None

        if chat_history_context:
            chat_history_context = f"### Conversation_History\n{chat_history_context}"
        else:
            chat_history_context = None

        # user_prompt = rag text context + stories context (if keywords detected) + chat history + user query
        context_list = [image_context, doc_context, story_context, chat_history_context, user_message]
        user_prompt = "\n\n".join(filter(None, context_list))  # filter out None values

        return user_prompt
    
    def _get_profile(self, mode) -> Optional[dict]:
        profile = None
        if mode == ChatbotPromptBuilder.MODE_APP:
            profile = self.profile_app
        elif mode == ChatbotPromptBuilder.MODE_TECHNICAL:
            profile = self.profile_technical
        elif mode == ChatbotPromptBuilder.MODE_PERSONA:
            profile = self.profile_persona

        return profile

    def get_story_by_memory_triggers(self, mode) -> Optional[dict]:
        profile = self._get_profile(mode)
        if profile is None:
            profile = self._load_profile_for_mode(mode)

        return profile.get("boundaries").get("story_by_memory_triggers")

    def _get_profile_for_mode(self, mode: str) -> Optional[dict]:
        if mode == ChatbotPromptBuilder.MODE_APP:
            if self.profile_app:
                return self.profile_app
            return self._load_profile_for_mode(mode)
        elif mode == ChatbotPromptBuilder.MODE_TECHNICAL:
            if self.profile_technical:
                return self.profile_technical
            return self._load_profile_for_mode(mode)
        elif mode == ChatbotPromptBuilder.MODE_PERSONA:
            if self.profile_persona:
                return self.profile_persona
            return self._load_profile_for_mode(mode)
        
        raise ValueError(f"Invalid mode: {mode}. Expected one of {ChatbotPromptBuilder.MODE_APP}, {ChatbotPromptBuilder.MODE_TECHNICAL}, {ChatbotPromptBuilder.MODE_PERSONA}.") 
            
    def _load_profile_for_mode(self, mode: str) -> Optional[dict]:
        profile_path_str = self.config.get("chatbot", "profile_path")
        profile_file_names = (self.config.get("chatbot", f"load_{mode}_profile")).split(",")
        profile_file_names = [p.strip() for p in profile_file_names]
        
        base_dir = Path(__file__).parent  # points to backend/
        profile_path = (base_dir / profile_path_str).resolve()

        merged_profile = {}
        for profile_file_name in profile_file_names:
            profile_file_path = profile_path / profile_file_name

            if self.debug:
                print(f"{self.__class__.__name__} 🔍 Loading profile: {profile_file_path}")

            try:
                with open(profile_file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    template = Template(content)
                    substituted = template.substitute(app_name=self.app_name, bot_name=self.bot_name)
                    profile_data = json.loads(substituted)
                    merged_profile.update(profile_data)  # merge into final dict

            except FileNotFoundError:
                self.app_logger.error(f"{self.__class__.__name__} Missing profile: {profile_file_path}")
                continue
            except json.JSONDecodeError as e:
                self.app_logger.error(f"{self.__class__.__name__} JSON error in profile {profile_file_path}: {e}")
                continue

        # update the profile for the specific mode
        if mode == ChatbotPromptBuilder.MODE_PERSONA:
            self.profile_persona = merged_profile
        elif mode == ChatbotPromptBuilder.MODE_TECHNICAL:   
            self.profile_technical = merged_profile
        elif mode == ChatbotPromptBuilder.MODE_APP:
            self.profile_app = merged_profile
    
        return merged_profile if merged_profile else None

    def _filter_visible(self, items: list[dict], system_mode: bool) -> list[str]:
        return [
            item["text"] for item in items
            if item.get("system_visibility", not system_mode)  # default True for persona, False for system
        ]

    def _smart_join(self, entries:dict, prefix:str="- ", sep=": "):
        joined_str = ""
        for key, value in entries.items():
          joined_str += f"{prefix}{key}{sep}{value}\n"
        return joined_str

    def _smart_join(self, items:list[str], prefix:str="", sep:str=", ", last_sep:str="and"):
        """
        Join a list of strings with a given separator and custom last separator (e.g., 'and' or 'or').

        Parameters:
        - items: list of strings to join
        - sep: separator between all items except the last (default: ', ')
        - last_sep: the word to use before the final item (default: 'and')

        Returns:
        - A string that joins the items nicely using sep and last_sep
        """
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return f"{sep.join(items[:-1])} {last_sep} {items[-1]}"

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