import json
from typing import Any, Dict, Union
from call_ai_function import call_ai_function
from config import Config
from json_utils import correct_json
from logger import logger

cfg = Config()

JSON_SCHEMA = """
{
    "command": {
        "name": "command name",
        "args":{
            "arg name": "value"
        }
    },
    "thoughts":
    {
        "text": "thought",
        "reasoning": "reasoning",
        "plan": "- short bulleted\n- list that conveys\n- long-term plan",
        "criticism": "constructive self-criticism",
        "speak": "thoughts summary to say to user"
    }
}
"""


def fix_and_parse_json(
    json_str: str,
    try_to_fix_with_gpt: bool = True
) -> Union[str, Dict[Any, Any]]:
    """Fix and parse JSON string"""
    try:
        json_str = json_str.replace('\t', '')
        return json.loads(json_str)
    except json.JSONDecodeError as _:  # noqa: F841
        try:
            json_str = correct_json(json_str)
            return json.loads(json_str)
        except json.JSONDecodeError as _:  # noqa: F841
            pass
    # Let's do something manually:
    # sometimes GPT responds with something BEFORE the braces:
    # "I'm sorry, I don't understand. Please try again."
    # {"text": "I'm sorry, I don't understand. Please try again.",
    #  "confidence": 0.0}
    # So let's try to find the first brace and then parse the rest
    #  of the string
    try:
        brace_index = json_str.index("{")
        json_str = json_str[brace_index:]
        last_brace_index = json_str.rindex("}")
        json_str = json_str[:last_brace_index+1]
        return json.loads(json_str)
    # Can throw a ValueError if there is no "{" or "}" in the json_str
    except (json.JSONDecodeError, ValueError) as e:  # noqa: F841
        if try_to_fix_with_gpt:
            logger.warn("Attention : Échec de l'analyse de la sortie de l'IA, tentative de correction."
            "\n Si vous voyez cet avertissement fréquemment, il est probable que"
            " votre demande est confuse pour l'IA. Essayez de la modifier légèrement.")
            # Now try to fix this up using the ai_functions
            ai_fixed_json = fix_json(json_str, JSON_SCHEMA)

            if ai_fixed_json != "failed":
                return json.loads(ai_fixed_json)
            else:
                # This allows the AI to react to the error message,
                #   which usually results in it correcting its ways.
                logger.error("Échec de la correction de la sortie de l'IA, en informant l'IA.")
                return json_str
        else:
            raise e


def fix_json(json_str: str, schema: str) -> str:
    """Fix the given JSON string to make it parseable and fully compliant with the provided schema."""
    # Try to fix the JSON using GPT:
    function_string = "def fix_json(json_str: str, schema:str=None) -> str:"
    args = [f"'''{json_str}'''", f"'''{schema}'''"]
    description_string = "Corrige la chaîne JSON fournie pour la rendre analysable et entièrement conforme au schéma fourni. "
    "Si un objet ou un champ spécifié dans le schéma n'est pas contenu dans le JSON correct, il est omis. "
    "Cette fonction est brillante pour deviner lorsque le format est incorrect."

    # If it doesn't already start with a "`", add one:
    if not json_str.startswith("`"):
        json_str = "```json\n" + json_str + "\n```"
    result_string = call_ai_function(
        function_string, args, description_string, model=cfg.fast_llm_model
    )
    logger.debug("------------ JSON TENTATIVE DE CORRECTION ---------------")
    logger.debug(f"JSON Original : {json_str}")
    logger.debug("-----------")
    logger.debug(f"JSON Corrigé: {result_string}")
    logger.debug("----------- JSON FIN DE CORRECTION ----------------")

    try:
        json.loads(result_string)  # just check the validity
        return result_string
    except:  # noqa: E722
        # Get the call stack:
        # import traceback
        # call_stack = traceback.format_exc()
        # print(f"Failed to fix JSON: '{json_str}' "+call_stack)
        return "failed"
