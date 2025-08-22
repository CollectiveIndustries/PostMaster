# Interactive script to generate config.ini
import os  # FIXME pylint: W0611: Unused import os (unused-import)  # FIXME pylint: E0011: Unrecognized file option 'unused-import' (unrecognized-inline-option)

if __name__ == "__main__":
    output_path = get_user_input(  # FIXME pylint: E0602: Undefined variable 'get_user_input' (undefined-variable)
        "Enter path to save config file", "/etc/SpamVanquisher/config.ini"
    )  # FIXME pylint: E0602: Undefined variable 'get_user_input' (undefined-variable)  # FIXME pylint: E0011: Unrecognized file option 'undefined-variable' (unrecognized-inline-option)
    generate_config_file(  # FIXME pylint: E0602: Undefined variable 'generate_config_file' (undefined-variable)
        output_path
    )  # FIXME pylint: E0602: Undefined variable 'generate_config_file' (undefined-variable)  # FIXME pylint: E0011: Unrecognized file option 'undefined-variable' (unrecognized-inline-option)
