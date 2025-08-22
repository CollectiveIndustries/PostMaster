# Interactive script to generate config.ini
import os

if __name__ == "__main__":
    output_path = get_user_input("Enter path to save config file", "/etc/SpamVanquisher/config.ini")
    generate_config_file(output_path)
