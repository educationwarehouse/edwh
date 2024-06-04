import hashlib
import json
from typing import Optional

import anyio
from invoke import Context


def string_to_ansi_color_code(input_string):
    # Generate a SHA1 hash of the input string
    hash_object = hashlib.sha1(input_string.encode())
    hex_dig = hash_object.hexdigest()

    # Take the first 6 characters of the hash as the color code
    color_code = hex_dig[:6]

    # Convert the color code to an ANSI escape sequence
    ansi_color_code = f"\033[38;2;{int(color_code[:2], 16)};{int(color_code[2:4], 16)};{int(color_code[4:], 16)}m"

    return ansi_color_code


def in_color(input_string: str, hash_string: Optional[str] = None):
    # Get the ANSI color code for the input string
    color_code = string_to_ansi_color_code(hash_string or input_string)

    # the input string in color and then reset the color
    return f"{color_code}{input_string}\033[0m"


async def parse_docker_log_line(line: str, human_name: str, container_id: str):
    # py4web-1  | [X] loaded _dashboard
    data = json.loads(line)

    print(in_color(human_name, container_id), "|", data.get("log"), end="")


async def tail(filename: str, human_name: str, container_id: str):
    async with await anyio.open_file(filename) as f:
        while True:
            if contents := await f.readline():
                await parse_docker_log_line(contents, human_name, container_id)
