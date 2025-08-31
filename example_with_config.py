from pathlib import Path

from dashc.single_module import dashc_module

# Generate the command for the test_project directory, targeting the my_app module
command = dashc_module(Path("my_app"), entrypoint="my_app")

print("Run this command:\n")
print(command)