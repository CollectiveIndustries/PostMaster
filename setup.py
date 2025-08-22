# Interactive script to generate config.ini
import os  # FIXME pylint: W0611: Unused import os (unused-import)

if __name__ == "__main__":
    output_path = get_user_input(
        "Enter path to save config file", "/etc/SpamVanquisher/config.ini"
    )  # FIXME pylint: E0602: Undefined variable 'get_user_input' (undefined-variable)
    generate_config_file(
        output_path
    )  # FIXME pylint: E0602: Undefined variable 'generate_config_file' (undefined-variable)
