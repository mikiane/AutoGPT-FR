from config import Config

cfg = Config()

from llm_utils import create_chat_completion
# This is a magic function that can do anything with no-code. See
# https://github.com/Torantulino/AI-Functions for more info.
def call_ai_function(function, args, description, model=None):
    """Call an AI function"""
    if model is None:
        model = cfg.smart_llm_model
    # For each arg, if any are None, convert to "None":
    args = [str(arg) if arg is not None else "None" for arg in args]
    # parse args to comma seperated string
    args = ", ".join(args)
    messages = [
        {
            "role": "system",
            "content": f"Tu es maintenant la fonction python suivante : ```# {description}\n{function}```\n\nNe réponds qu'avec ta valeur `return`",
        },
        {"role": "user", "content": args},
    ]

    response = create_chat_completion(
        model=model, messages=messages, temperature=0
    )

    return response
