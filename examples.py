import dashc
from pathlib import Path
import subprocess

def main():
    # 1. Write example source.py
    source_py = Path("example.py")
    source_py.write_text("""print('Hello from inside example.py!')""", encoding="utf-8")

    # 2. Call dashc()
    cmd = dashc.single_file.dashc(source_py)

    # 3. Write out.sh
    Path("out.sh").write_text("#!/usr/bin/env bash\n" + cmd + "\n", encoding="utf-8")

    # 4. Attempt execution
    print("Running out.sh...\n")
    result = subprocess.run(["bash", "./out.sh"], capture_output=True, text=True, check=True)
    print("STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)


if __name__ == "__main__":
    main()
