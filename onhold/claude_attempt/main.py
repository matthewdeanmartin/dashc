import shlex

# assume hello.py is executable, no escaping issues.
with open("hello.py") as hello:
    # escapes and adds quotes suitable for bash, I guess.
    escaped_bash =shlex.quote(hello.read())
print(escaped_bash)

# this prints suitable bash code.
print(f"python -c {escaped_bash}")