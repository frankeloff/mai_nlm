"""Исполнение LLM_Theatre.ipynb headless (nbclient) с сохранением выходов."""
import nbformat
from nbclient import NotebookClient

nb = nbformat.read("LLM_Theatre.ipynb", as_version=4)
client = NotebookClient(nb, timeout=1800, kernel_name="theatre",
                        resources={"metadata": {"path": "."}})
client.execute()
nbformat.write(nb, "LLM_Theatre.ipynb")
print("Выполнено, выходы сохранены")
