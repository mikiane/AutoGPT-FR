import browse
import json
from memory import get_memory
import datetime
import agent_manager as agents
import speak
from config import Config
import ai_functions as ai
from file_operations import read_file, write_to_file, append_to_file, delete_file, search_files
from execute_code import execute_python_file, execute_shell
from json_parser import fix_and_parse_json
from image_gen import generate_image
from duckduckgo_search import ddg
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

cfg = Config()


def is_valid_int(value):
    try:
        int(value)
        return True
    except ValueError:
        return False

def get_command(response):
    """Analyse la réponse et renvoie le nom de la commande et les arguments."""
    try:
        response_json = fix_and_parse_json(response)

        if "command" not in response_json:
            return "Erruer:" , "Objet 'command' manquant dans le JSON"

        command = response_json["command"]

        if "name" not in command:
            return "Erruer:", "Champ 'nom' manquant dans l'objet 'commande'."

        command_name = command["name"]

        # Use an empty dictionary if 'args' field is not present in 'command' object
        arguments = command.get("args", {})

        return command_name, arguments
    except json.decoder.JSONDecodeError:
        return "Erruer:", "JSON Invalide"
    # All other errors, return "Error: + error message"
    except Exception as e:
        return "Error:", str(e)


def execute_command(command_name, arguments):
    """Exécuter la commande et renvoyer le résultat"""
    memory = get_memory(cfg)

    try:
        if command_name == "google":

            # Check if the Google API key is set and use the official search method
            # If the API key is not set or has only whitespaces, use the unofficial search method
            if cfg.google_api_key and (cfg.google_api_key.strip() if cfg.google_api_key else None):
                return google_official_search(arguments["input"])
            else:
                return google_search(arguments["input"])
        elif command_name == "memory_add":
            return memory.add(arguments["string"])
        elif command_name == "start_agent":
            return start_agent(
                arguments["name"],
                arguments["task"],
                arguments["prompt"])
        elif command_name == "message_agent":
            return message_agent(arguments["key"], arguments["message"])
        elif command_name == "list_agents":
            return list_agents()
        elif command_name == "delete_agent":
            return delete_agent(arguments["key"])
        elif command_name == "get_text_summary":
            return get_text_summary(arguments["url"], arguments["question"])
        elif command_name == "get_hyperlinks":
            return get_hyperlinks(arguments["url"])
        elif command_name == "read_file":
            return read_file(arguments["file"])
        elif command_name == "write_to_file":
            return write_to_file(arguments["file"], arguments["text"])
        elif command_name == "append_to_file":
            return append_to_file(arguments["file"], arguments["text"])
        elif command_name == "delete_file":
            return delete_file(arguments["file"])
        elif command_name == "search_files":
            return search_files(arguments["directory"])
        elif command_name == "browse_website":
            return browse_website(arguments["url"], arguments["question"])
        # TODO: Change these to take in a file rather than pasted code, if
        # non-file is given, return instructions "Input should be a python
        # filepath, write your code to file and try again"
        elif command_name == "evaluate_code":
            return ai.evaluate_code(arguments["code"])
        elif command_name == "improve_code":
            return ai.improve_code(arguments["suggestions"], arguments["code"])
        elif command_name == "write_tests":
            return ai.write_tests(arguments["code"], arguments.get("focus"))
        elif command_name == "execute_python_file":  # Add this command
            return execute_python_file(arguments["file"])
        elif command_name == "execute_shell":
            if cfg.execute_local_commands:
                return execute_shell(arguments["command_line"])
            else:
                return "Vous n'êtes pas autorisé à exécuter des commandes shell locales. Pour exécuter des commandes shell, EXECUTE_LOCAL_COMMANDS doit avoir la valeur 'True' dans votre configuration. N'essayez pas de contourner cette restriction."
        elif command_name == "generate_image":
            return generate_image(arguments["prompt"])
        elif command_name == "do_nothing":
            return "Pa sd'action réalisée"
        elif command_name == "task_complete":
            shutdown()
        else:
            return f"Commande inconnue '{command_name}'. Veuillez consulter la liste des 'COMMANDES' pour connaître les commandes disponibles et ne répondez que dans le format JSON spécifié."
    # All errors, return "Error: + error message"
    except Exception as e:
        return "Erruer: " + str(e)


def get_datetime():
    """Renvoi de la date et de l'heure actuelles"""
    return "Date et heure actuelles :" + \
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def google_search(query, num_results=8):
    """Renvoyer les résultats d'une recherche Google"""
    search_results = []
    for j in ddg(query, max_results=num_results):
        search_results.append(j)

    return json.dumps(search_results, ensure_ascii=False, indent=4)

def google_official_search(query, num_results=8):
    """Renvoyer les résultats d'une recherche Google en utilisant l'API officielle de Google"""
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    import json

    try:
        # Get the Google API key and Custom Search Engine ID from the config file
        api_key = cfg.google_api_key
        custom_search_engine_id = cfg.custom_search_engine_id

        # Initialize the Custom Search API service
        service = build("customsearch", "v1", developerKey=api_key)

        # Send the search query and retrieve the results
        result = service.cse().list(q=query, cx=custom_search_engine_id, num=num_results).execute()

        # Extract the search result items from the response
        search_results = result.get("items", [])

        # Create a list of only the URLs from the search results
        search_results_links = [item["link"] for item in search_results]

    except HttpError as e:
        # Handle errors in the API call
        error_details = json.loads(e.content.decode())

        # Check if the error is related to an invalid or missing API key
        if error_details.get("error", {}).get("code") == 403 and "invalid API key" in error_details.get("error", {}).get("message", ""):
            return "Erreur: La clé Google API fournie n'est pas valide ou est manquante."
        else:
            return f"Error: {e}"

    # Return the list of search result URLs
    return search_results_links

def browse_website(url, question):
    """Browse a website and return the summary and links"""
    summary = get_text_summary(url, question)
    links = get_hyperlinks(url)

    # Limit links to 5
    if len(links) > 5:
        links = links[:5]

    result = f"""Résumé du contenu du site Internet : {summary}\n\Liens: {links}"""

    return result


def get_text_summary(url, question):
    """Return the results of a google search"""
    text = browse.scrape_text(url)
    summary = browse.summarize_text(text, question)
    return """ "Resultats" : """ + summary


def get_hyperlinks(url):
    """Return the results of a google search"""
    link_list = browse.scrape_links(url)
    return link_list


def commit_memory(string):
    """Commit a string to memory"""
    _text = f"""Enregistrer la mémoire avec une chaîne de caractères "{string}" """
    mem.permanent_memory.append(string)
    return _text


def delete_memory(key):
    """Delete a memory with a given key"""
    if key >= 0 and key < len(mem.permanent_memory):
        _text = "Effacement de la mémoire avec la clé " + str(key)
        del mem.permanent_memory[key]
        print(_text)
        return _text
    else:
        print("Clé non valide, impossible d'effacer la mémoire.")
        return None


def overwrite_memory(key, string):
    """Overwrite a memory with a given key and string"""
    # Check if the key is a valid integer
    if is_valid_int(key):
        key_int = int(key)
        # Check if the integer key is within the range of the permanent_memory list
        if 0 <= key_int < len(mem.permanent_memory):
            _text = "Ecraser la mémoire avec la clé " + str(key) + " et la chaine " + string
            # Overwrite the memory slot with the given integer key and string
            mem.permanent_memory[key_int] = string
            print(_text)
            return _text
        else:
            print(f"Clé invalide '{key}', hors de portée.")
            return None
    # Check if the key is a valid string
    elif isinstance(key, str):
        _text = "Ecraser la mémoire avec la clé " + key + " et la chaine " + string
        # Overwrite the memory slot with the given string key and string
        mem.permanent_memory[key] = string
        print(_text)
        return _text
    else:
        print(f"Clé invalide '{key}', doit être un nombre entier ou une chaîne de caractères.")
        return None


def shutdown():
    """Shut down the program"""
    print("Arret...")
    quit()


def start_agent(name, task, prompt, model=cfg.fast_llm_model):
    """Start an agent with a given name, task, and prompt"""
    global cfg

    # Remove underscores from name
    voice_name = name.replace("_", " ")

    first_message = f"""Tu es {name}.  Répondre par : "Accusé de réception"."""
    agent_intro = f"{voice_name} ici, au rapport !"

    # Create agent
    if cfg.speak_mode:
        speak.say_text(agent_intro, 1)
    key, ack = agents.create_agent(task, first_message, model)

    if cfg.speak_mode:
        speak.say_text(f"Hello {voice_name}. Votre tâche est la suivante. {task}.")

    # Assign task (prompt), get response
    agent_response = message_agent(key, prompt)

    return f"L'Agent {name} créé avec la clé {key}. Première réponse : {agent_response}"


def message_agent(key, message):
    """Message an agent with a given key and message"""
    global cfg

    # Check if the key is a valid integer
    if is_valid_int(key):
        agent_response = agents.message_agent(int(key), message)
    # Check if the key is a valid string
    elif isinstance(key, str):
        agent_response = agents.message_agent(key, message)
    else:
        return "Clé non valide, doit être un entier ou une chaîne."

    # Speak response
    if cfg.speak_mode:
        speak.say_text(agent_response, 1)
    return agent_response


def list_agents():
    """List all agents"""
    return agents.list_agents()


def delete_agent(key):
    """Delete an agent with a given key"""
    result = agents.delete_agent(key)
    if not result:
        return f"L'Agent {key} n'existe pas"
    return f"L'agent {key} effacé."
