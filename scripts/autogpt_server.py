import asyncio
import websockets
import json
import random
import commands as cmd
import utils
from memory import get_memory, get_supported_memory_backends
import data
import chat
from colorama import Fore, Style
from spinner import Spinner
import time
import speak
from config import Config
from json_parser import fix_and_parse_json
from ai_config import AIConfig
import traceback
import yaml
import argparse
from logger import logger
import logging

async def send_log(websocket, log_message):
    try:
        await websocket.send(f"LOG: {log_message}")
    except Exception as e:
        print(f"Erreur lors de l'envoi du message de log : {e}")

class WebSocketLogger(logging.Handler):
    def __init__(self, websocket):
        super().__init__()
        self.websocket = websocket

    def emit(self, record):
        log_message = self.format(record)
        asyncio.create_task(send_log(self.websocket, log_message))


cfg = Config()

async def check_openai_api_key(websocket):
    """Check if the OpenAI API key is set in config.py or as an environment variable."""
    if not cfg.openai_api_key:
        await websocket.send(
            Fore.RED +
            "Veuillez définir votre clé API OpenAI dans config.py ou en tant que variable d'environnement."
        )
        await websocket.send("Récupérer votre clé sur https://beta.openai.com/account/api-keys")
        exit(1)

async def attempt_to_fix_json_by_finding_outermost_brackets(json_string, websocket):
    if cfg.speak_mode and cfg.debug_mode:
      speak.say_text("J'ai reçu une réponse JSON invalide de l'API OpenAI. J'essaie de la corriger maintenant.")
    await websocket.send("Tentative de correction du JSON en trouvant les crochets extérieurs\n")

    try:
        # Use regex to search for JSON objects
        import regex
        json_pattern = regex.compile(r"\{(?:[^{}]|(?R))*\}")
        json_match = json_pattern.search(json_string)

        if json_match:
            # Extract the valid JSON object from the string
            json_string = json_match.group(0)
            await websocket.send(title="Apparemment, le JSON a été corrigé.", title_color=Fore.GREEN)
            if cfg.speak_mode and cfg.debug_mode:
               speak.say_text("AApparemment, le JSON a été corrigé.")
        else:
            raise ValueError("Aucun objet JSON valide trouvé")

    except (json.JSONDecodeError, ValueError) as e:
        if cfg.speak_mode:
            speak.say_text("N'a pas fonctionné. Je devrai alors ignorer cette réponse.")
        await websocket.send("Erreur : JSON invalide, le réinitialisant en JSON vide maintenant.\n")
        json_string = {}

    return json_string

async def print_assistant_thoughts(assistant_reply, websocket):
    """Prints the assistant's thoughts to the console"""
    global ai_name
    global cfg
    try:
        try:
            # Parse and print Assistant response
            assistant_reply_json = fix_and_parse_json(assistant_reply)
        except json.JSONDecodeError as e:
            await websocket.send("Erreur : JSON non valide dans les pensées de l'assistant\n", assistant_reply)
            assistant_reply_json = attempt_to_fix_json_by_finding_outermost_brackets(assistant_reply, websocket)
            assistant_reply_json = fix_and_parse_json(assistant_reply_json)

        # Check if assistant_reply_json is a string and attempt to parse it into a JSON object
        if isinstance(assistant_reply_json, str):
            try:
                assistant_reply_json = json.loads(assistant_reply_json)
            except json.JSONDecodeError as e:
                await websocket.send("Erreur: JSON invalide\n", assistant_reply)
                assistant_reply_json = attempt_to_fix_json_by_finding_outermost_brackets(assistant_reply_json, websocket)

        assistant_thoughts_reasoning = None
        assistant_thoughts_plan = None
        assistant_thoughts_speak = None
        assistant_thoughts_criticism = None
        assistant_thoughts = assistant_reply_json.get("thoughts", {})
        assistant_thoughts_text = assistant_thoughts.get("text")

        if assistant_thoughts:
            assistant_thoughts_reasoning = assistant_thoughts.get("reasoning")
            assistant_thoughts_plan = assistant_thoughts.get("plan")
            assistant_thoughts_criticism = assistant_thoughts.get("criticism")
            assistant_thoughts_speak = assistant_thoughts.get("speak")

        await websocket.send(f"{ai_name.upper()} PENSÉES:", Fore.YELLOW, assistant_thoughts_text)
        await websocket.send("RAISONNEMENT:", Fore.YELLOW, assistant_thoughts_reasoning)

        if assistant_thoughts_plan:
            await websocket.send("PLAN:", Fore.YELLOW, "")
            # If it's a list, join it into a string
            if isinstance(assistant_thoughts_plan, list):
                assistant_thoughts_plan = "\n".join(assistant_thoughts_plan)
            elif isinstance(assistant_thoughts_plan, dict):
                assistant_thoughts_plan = str(assistant_thoughts_plan)

            # Split the input_string using the newline character and dashes
            lines = assistant_thoughts_plan.split('\n')
            for line in lines:
                line = line.lstrip("- ")
                await websocket.send("- ", Fore.GREEN, line.strip())

        await websocket.send("CRITIQUE:", Fore.YELLOW, assistant_thoughts_criticism)
        # Speak the assistant's thoughts
        if cfg.speak_mode and assistant_thoughts_speak:
            speak.say_text(assistant_thoughts_speak)

        return assistant_reply_json
    except json.decoder.JSONDecodeError as e:
        await websocket.send("Erreur : JSON invalide\n", assistant_reply)
        if cfg.speak_mode:
            speak.say_text("J'ai reçu une réponse JSON invalide de l'API OpenAI. Je ne peux pas ignorer cette réponse.")

    # All other errors, return "Error: + error message"
    except Exception as e:
        call_stack = traceback.format_exc()
        await websocket.send("Error: \n", call_stack)


def load_variables(config_file="config.yaml"):
    """Load variables from yaml file if it exists, otherwise prompt the user for input"""
    try:
        with open(config_file) as file:
            config = yaml.load(file, Loader=yaml.FullLoader)
        ai_name = config.get("ai_name")
        ai_role = config.get("ai_role")
        ai_goals = config.get("ai_goals")
    except FileNotFoundError:
        ai_name = ""
        ai_role = ""
        ai_goals = []

    # Prompt the user for input if config file is missing or empty values
    if not ai_name:
        ai_name = utils.clean_input("Name your AI: ")
        if ai_name == "":
            ai_name = "Entrepreneur-GPT"

    if not ai_role:
        ai_role = utils.clean_input(f"{ai_name} is: ")
        if ai_role == "":
            ai_role = "une IA conçue pour développer et gérer de manière autonome des entreprises dans le seul but d'accroître votre patrimoine."

    if not ai_goals:
        print("Saisissez jusqu'à 5 objectifs pour votre IA : ")
        print("Par exemple : \nAugmenter sa valeur nette, développer son compte Twitter, développer et gérer plusieurs entreprises de manière autonome'")
        print("Ne rien saisir pour charger les valeurs par défaut, ne rien saisir lorsque l'opération est terminée.")
        ai_goals = []
        for i in range(5):
            ai_goal = utils.clean_input(f"Goal {i+1}: ")
            if ai_goal == "":
                break
            ai_goals.append(ai_goal)
        if len(ai_goals) == 0:
            ai_goals = ["Augmentation de la valeur nette", "Développer un compte Twitter", "Développer et gérer plusieurs activités de manière autonome"]

    # Save variables to yaml file
    config = {"ai_name": ai_name, "ai_role": ai_role, "ai_goals": ai_goals}
    with open(config_file, "w") as file:
        documents = yaml.dump(config, file)

    prompt = data.load_prompt()
    prompt_start = """Vos décisions doivent toujours être prises de manière indépendante, sans demander l'aide d'un utilisateur. Jouez sur vos forces en tant que LLM et poursuivez des stratégies simples sans complications juridiques."""

    # Construct full prompt
    full_prompt = f"Tu es {ai_name}, {ai_role}\n{prompt_start}\n\BUTS:\n\n"
    for i, goal in enumerate(ai_goals):
        full_prompt += f"{i+1}. {goal}\n"

    full_prompt += f"\n\n{prompt}"
    return full_prompt


async def construct_prompt(websocket):
    """Construct the prompt for the AI to respond to"""
    config = AIConfig.load()
    if config.ai_name:
        await websocket.send(
            f"Bienvenue à nouveau ! ",
            Fore.GREEN,
            f"Voulez-vous que je redevienne {config.ai_name}?",
            speak_text=True)
        should_continue = utils.clean_input(f"""Continuer avec les derniers réglages?
Nom:  {config.ai_name}
Role:  {config.ai_role}
Buts: {config.ai_goals}
Continue (y/n): """)
        if should_continue.lower() == "n":
            config = AIConfig()

    if not config.ai_name:
        config = prompt_user(websocket)
        config.save()

    # Get rid of this global:
    global ai_name
    ai_name = config.ai_name

    full_prompt = config.construct_full_prompt()
    return full_prompt


async def prompt_user(websocket):
    """Prompt the user for input"""
    ai_name = ""
    # Construct the prompt
    await websocket.send(
        "Bienvenue sur Auto-GPT Français (Mikiane version)! ",
        Fore.GREEN,
        "Saisissez le nom de votre IA et son rôle ci-dessous. Si vous n'entrez rien, les paramètres par défaut seront chargés.",
        speak_text=True)

    # Get AI Name from User
    await websocket.send(
        "Nom de votre IA: ",
        Fore.GREEN,
        "Par exemple, 'Entrepreneur-GPT'")
    ai_name = utils.clean_input("AI Name: ")
    if ai_name == "":
        ai_name = "Entrepreneur-GPT"

    await websocket.send(
        f"{ai_name} présent !",
        Fore.LIGHTBLUE_EX,
        "Je suis à votre service.",
        speak_text=True)

    # Get AI Role from User
    await websocket.send(
        "Décrivez le rôle de votre IA : ",
        Fore.GREEN,
        "Par exemple, une IA conçue pour développer et gérer de manière autonome des entreprises dans le seul but d'accroître votre patrimoine net")
    ai_role = utils.clean_input(f"{ai_name} est : ")
    if ai_role == "":
        ai_role = "une IA conçue pour développer et gérer de manière autonome des entreprises dans le seul but d'accroître votre patrimoine."

    # Enter up to 5 goals for the AI
    await websocket.send(
        "Saisissez jusqu'à 5 objectifs pour votre IA :",
        Fore.GREEN,
        "Par exemple : \nAugmenter sa valeur nette, développer son compte Twitter, développer et gérer plusieurs activités de manière autonome")
    await websocket.send("Ne rien saisir pour charger les valeurs par défaut, ne rien saisir lorsque l'opération est terminée.", flush=True)
    ai_goals = []
    for i in range(5):
        ai_goal = utils.clean_input(f"{Fore.LIGHTBLUE_EX}Goal{Style.RESET_ALL} {i+1}: ")
        if ai_goal == "":
            break
        ai_goals.append(ai_goal)
    if len(ai_goals) == 0:
        ai_goals = ["Augmentation de la valeur nette", "Développer le compte Twitter",
                    "Développer et gérer plusieurs activités de manière autonome"]

    config = AIConfig(ai_name, ai_role, ai_goals)
    return config

async def parse_arguments(websocket):
    """Parses the arguments passed to the script"""
    global cfg
    cfg.set_debug_mode(False)
    cfg.set_continuous_mode(False)
    cfg.set_speak_mode(False)

    parser = argparse.ArgumentParser(description='Arguments de processus')
    parser.add_argument('--continuous', action='store_true', help='Activer le mode continu')
    parser.add_argument('--speak', action='store_true', help='Activer le mode conversation')
    parser.add_argument('--debug', action='store_true', help='Activer le mode débogage')
    parser.add_argument('--gpt3only', action='store_true', help='Activer le mode GPT3.5 uniquement')
    parser.add_argument('--gpt4only', action='store_true', help='Activer le mode GPT4 uniquement')
    parser.add_argument('--use-memory', '-m', dest="memory_type", help='Définit le système de gestion de la mémoire à utiliser')
    args = parser.parse_args()

    if args.debug:
        await websocket.send("Mode Debug: ", Fore.GREEN, "ENABLED")
        cfg.set_debug_mode(True)

    if args.continuous:
        await websocket.send("Mode Continue: ", Fore.RED, "ENABLED")
        await websocket.send(
            "ATTENTION: ",
            Fore.RED,
            "Le mode continu n'est pas recommandé. Il est potentiellement dangereux et peut faire tourner votre IA à l'infini ou effectuer des actions que vous n'auriez pas normalement autorisées. Utilisez-le à vos risques et périls.")
        cfg.set_continuous_mode(True)

    if args.speak:
        await websocket.send("Mode voix: ", Fore.GREEN, "ENABLED")
        cfg.set_speak_mode(True)

    if args.gpt3only:
        await websocket.send("GPT3.5 Mode: ", Fore.GREEN, "ENABLED")
        cfg.set_smart_llm_model(cfg.fast_llm_model)

    if args.gpt4only:
        await websocket.send("GPT4 Mode: ", Fore.GREEN, "ENABLED")
        cfg.set_fast_llm_model(cfg.smart_llm_model)

    if args.debug:
        await websocket.send("Mode Debug : ", Fore.GREEN, "ENABLED")
        cfg.set_debug_mode(True)

    if args.memory_type:
        supported_memory = get_supported_memory_backends()
        chosen = args.memory_type
        if not chosen in supported_memory:
            print_to_console("SEULS LES BACKENDS DE MÉMOIRE SUIVANTS SONT PRIS EN CHARGE : ", Fore.RED, f'{supported_memory}')
            print_to_console(f"Par défaut : ", Fore.YELLOW, cfg.memory_backend)
        else:
            cfg.memory_backend = chosen

 



async def handle_client(websocket, path):
    # TODO: fill in llm values here
    check_openai_api_key(websocket)
    parse_arguments(websocket)
    logger.set_level(logging.DEBUG if cfg.debug_mode else logging.INFO)
    websocket_handler = WebSocketLogger(websocket)
    websocket_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(websocket_handler)
    
    ai_name = ""
    prompt = construct_prompt(websocket)
    # Initialize variables
    full_message_history = []
    result = None
    next_action_count = 0
    # Make a constant:
    user_input = "Déterminez la prochaine commande à utiliser et répondez en utilisant le format spécifié ci-dessus :"

    # Initialize memory and make sure it is empty.
    # this is particularly important for indexing and referencing pinecone memory
    memory = get_memory(cfg, init=True)
    await websocket.send('Utilisation de la mémoire de type : ' + memory.__class__.__name__)

    # Interaction Loop
    while True:
        # Send message to AI, get response
        with Spinner("Je réfléchis... "):
            assistant_reply = chat.chat_with_ai(
                prompt,
                user_input,
                full_message_history,
                memory,
                cfg.fast_token_limit)  # TODO: This hardcodes the model to use GPT3.5. Make this an argument

        # Print Assistant thoughts
        print_assistant_thoughts(assistant_reply, websocket)

        # Get command name and arguments
        try:
            command_name, arguments = cmd.get_command(attempt_to_fix_json_by_finding_outermost_brackets(assistant_reply, websocket))
            if cfg.speak_mode:
                speak.say_text(f"Je veux exécuter {command_name}")
        except Exception as e:
            await websocket.send("Erreur: \n", str(e))

        if not cfg.continuous_mode and next_action_count == 0:
            ### GET USER AUTHORIZATION TO EXECUTE COMMAND ###
            # Get key press: Prompt the user to press enter to continue or escape
            # to exit
            user_input = ""
            await websocket.send(
                f"Entrer 'y' pour autoriser la commande, 'y -N' pour executer N commandes continues, 'n' pour sortir du program, ou entrer un feedback à {ai_name}...")
            console_input = await websocket.recv()

            if console_input.lower().rstrip() == "y":
                user_input = "GÉNÉRER LE JSON DE LA PROCHAINE COMMANDE"
            elif console_input.lower().startswith("y -"):
                try:
                    next_action_count = abs(int(console_input.split(" ")[1]))
                    user_input = "GÉNÉRER LE JSON DE LA PROCHAINE COMMANDE"
                except ValueError:
                    await websocket.send("Format d'entrée non valide. Veuillez saisir 'y -n' où n est le nombre de tâches continues.")
                    continue
            elif console_input.lower() == "n":
                user_input = "EXIT"
            else:
                user_input = console_input
                command_name = "human_feedback"

            if user_input == "GÉNÉRER LE JSON DE LA PROCHAINE COMMANDE":
                await websocket.send(
                    "-=-=-=-=-=-=-= COMMANDE AUTORISEE PAR L'UTILISATEUR -=-=-=-=-=-=-=")
            elif user_input == "EXIT":
                await websocket.send("Sortie en cours...")
                break
        else:
            await websocket.send(
                f"NEXT ACTION: COMMANDE = {command_name}  ARGUMENTS = {arguments}")

        # Execute command
        if command_name is not None and command_name.lower().startswith("error"):
            result = f"Commande {command_name} a généré l'erreur suivante : " + arguments
        elif command_name == "human_feedback":
            result = f"Human feedback: {user_input}"
        else:
            result = f"la Commande {command_name} a retourné : {cmd.execute_command(command_name, arguments)}"
            if next_action_count > 0:
                next_action_count -= 1

        memory_to_add = f"Assistant Réponse: {assistant_reply} " \
                        f"\nResultat: {result} " \
                        f"\nFeedback humain: {user_input} "

        memory.add(memory_to_add)

        # Check if there's a result from the command append it to the message
        # history
        if result is not None:
            full_message_history.append(chat.create_chat_message("system", result))
            await websocket.send(f"SYSTEM: {result}")
        else:
            full_message_history.append(
                chat.create_chat_message(
                    "system", "Unable to execute command"))
            await websocket.send("SYSTEM: Unable to execute command")
        
