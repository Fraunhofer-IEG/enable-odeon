import unittest
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError


class TestDocExamples(unittest.TestCase):
    def test_execute_all_notebooks(self):
        notebook_folder = Path("docs/examples")
        files = [f for f in notebook_folder.iterdir() if f.is_file() and f.suffix == ".ipynb"]
        self.assertTrue(files, "No notebooks found in docs/examples")

        for file in files:
            with self.subTest(notebook=file.name):
                try:
                    nb = nbformat.read(str(file), as_version=4)
                    client = NotebookClient(
                        nb,
                        timeout=600,  # adjust if your notebooks take longer
                        kernel_name="python3",  # ensure your CI kernel matches
                        allow_errors=False,  # raise on first error
                    )
                    client.execute()
                    print(f"successfully tested {file}")
                except CellExecutionError as e:
                    print(f"exception in notebook {file}: {e}")
                    raise Exception(f"exception in notebook {file}: {e}")
                except UnicodeEncodeError as e:
                    print(f"exception in notebook {file}: {e}")
                    raise Exception(f"exception in notebook {file}: {e}")


if __name__ == "__main__":
    TestDocExamples().test_execute_all_notebooks()
