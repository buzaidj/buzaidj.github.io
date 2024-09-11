import re
import os


def include_html_content(source_file):
    include_pattern = re.compile(
        r'<!-- begin include "(.+?)" -->(.*?)<!-- end include "\1" -->',
        re.DOTALL
    )

    def fetch_include_content(match):
        include_file_name = match.group(1)
        include_file_path = os.path.join(os.path.dirname(source_file), include_file_name)
        try:
            with open(include_file_path, 'r', encoding='utf-8') as include_file:
                return f'<!-- begin include "{include_file_name}" -->\n' + include_file.read() + f'\n<!-- end include "{include_file_name}" -->'
        except FileNotFoundError:
            print(f"Warning: Include file {include_file_name} not found.")
            return match.group(0)

    with open(source_file, 'r', encoding='utf-8') as file:
        content = file.read()

    new_content = re.sub(include_pattern, fetch_include_content, content)

    with open(source_file, 'w', encoding='utf-8') as file:
        file.write(new_content)


if __name__ == "__main__":
    include_html_content('index.html')
