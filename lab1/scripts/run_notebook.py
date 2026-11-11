"""Исполнение Agent_Artist.ipynb headless (nbclient) с сохранением выходов."""
import nbformat
from nbclient import NotebookClient

nb = nbformat.read("Agent_Artist.ipynb", as_version=4)
client = NotebookClient(nb, timeout=3600, kernel_name="artist",
                        resources={"metadata": {"path": "."}})
client.execute()
nbformat.write(nb, "Agent_Artist.ipynb")
print("Выполнено, выходы сохранены")
