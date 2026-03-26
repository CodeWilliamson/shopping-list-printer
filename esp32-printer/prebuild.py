import os
Import("env")

def load_env_file(filepath=".env"):
    env_vars = {}

    if not os.path.exists(filepath):
        print(f"[WARN] {filepath} not found")
        return env_vars

    print(f"Loading {filepath}...")

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            # Remove surrounding quotes if present
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

            env_vars[key] = value

    return env_vars


def inject_defines(env_vars):
    defines = []

    for key, value in env_vars.items():
        # Escape quotes for C/C++
        escaped_value = value.replace('"', '\\"')

        defines.append((key, f'\\"{escaped_value}\\"'))

        # Also set for Python environment if needed
        os.environ[key] = value

        print(f"Injecting {key}={value}")

    env.Append(CPPDEFINES=defines)


# --- Main ---
env_file = ".env"
vars_from_env = load_env_file(env_file)
inject_defines(vars_from_env)