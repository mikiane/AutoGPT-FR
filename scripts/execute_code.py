import docker
import os
import subprocess


WORKSPACE_FOLDER = "auto_gpt_workspace"


def execute_python_file(file):
    """Execute a Python file in a Docker container and return the output"""

    print (f"Exécution du fichier '{file}' dans l'espace de travail '{WORKSPACE_FOLDER}'")

    if not file.endswith(".py"):
        return "Erreur : Type de fichier non valide. Seuls les fichiers .py sont autorisés."

    file_path = os.path.join(WORKSPACE_FOLDER, file)

    if not os.path.isfile(file_path):
        return f"Erreur : Fichier '{file}' n'existe pas."

    try:
        client = docker.from_env()

        image_name = 'python:3.10'
        try:
            client.images.get(image_name)
            print(f"Image '{image_name}' trouvée localement")
        except docker.errors.ImageNotFound:
            print(f"Image '{image_name}' non trouvé localement, tirée du Docker Hub")
            # Use the low-level API to stream the pull response
            low_level_client = docker.APIClient()
            for line in low_level_client.pull(image_name, stream=True, decode=True):
                # Print the status and progress, if available
                status = line.get('status')
                progress = line.get('progress')
                if status and progress:
                    print(f"{status}: {progress}")
                elif status:
                    print(status)

        # You can replace 'python:3.8' with the desired Python image/version
        # You can find available Python images on Docker Hub:
        # https://hub.docker.com/_/python
        container = client.containers.run(
            image_name,
            f'python {file}',
            volumes={
                os.path.abspath(WORKSPACE_FOLDER): {
                    'bind': '/workspace',
                    'mode': 'ro'}},
            working_dir='/workspace',
            stderr=True,
            stdout=True,
            detach=True,
        )

        output = container.wait()
        logs = container.logs().decode('utf-8')
        container.remove()

        # print(f"Execution complete. Output: {output}")
        # print(f"Logs: {logs}")

        return logs

    except Exception as e:
        return f"Erreur: {str(e)}"

def execute_shell(command_line):

    current_dir = os.getcwd()

    if not WORKSPACE_FOLDER in current_dir: # Change dir into workspace if necessary
        work_dir = os.path.join(os.getcwd(), WORKSPACE_FOLDER)
        os.chdir(work_dir)

    print (f"Exécution de la commande '{command_line}' dans le répertoire de travail '{os.getcwd()}'")

    result = subprocess.run(command_line, capture_output=True, shell=True)
    output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

    # Change back to whatever the prior working dir was

    os.chdir(current_dir)

    return output
