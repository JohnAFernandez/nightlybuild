import re
from typing import List, Tuple, Dict

import requests

from files import ReleaseFile
from files import SourceFile
from util import retry_multi, GLOBAL_TIMEOUT


def get_release_files(tag_name, config) -> Tuple[List[ReleaseFile], Dict[str, SourceFile]]:
    @retry_multi(5)
    def execute_request(path):
        headers = {
            "Accept": "application/vnd.github.v3+json"
        }
        url = "https://api.github.com" + path

        response = requests.get(url, headers=headers, timeout=GLOBAL_TIMEOUT)

        response.raise_for_status()

        return response.json()

    build_group_regex = re.compile("fs2_open_.*-builds-([^.-]*)(-([^.]*))?.*")
    source_file_regex = re.compile("fs2_open_.*-source-([^.]*)?.*")

    response = execute_request(
        "/repos/{}/{}/releases/tags/{}".format(config["github"]["user"], config["github"]["repo"], tag_name))

    binary_files = []
    source_files = {}
    for asset in response["assets"]:
        url = asset["browser_download_url"]
        name = asset["name"]

        group_match = build_group_regex.match(name)

        if group_match is not None:
            platform = group_match.group(1)
            # x64 is the Visual Studio name but for consistency we need Win64
            if platform == "x64":
                platform = "Win64"

            binary_files.append(ReleaseFile(name, url, platform, group_match.group(3)))
        else:
            group_match = source_file_regex.match(name)

            if group_match is None:
                continue

            group = group_match.group(1)

            source_files[group] = SourceFile(name, url, group)

    return binary_files, source_files


def get_nightly_files(tag_name, config):
    tag_regex = re.compile("nightly_(.*)")
    build_group_regex = re.compile("nightly_.*-builds-([^.]+).*")
    link_regex = re.compile(r'<a href="(nightly_[^"]+)"')

    version_str = tag_regex.match(tag_name).group(1)

    files = []
    for mirror in config["ftp"]["mirrors"]:
        url = mirror.format(type="nightly", version=version_str, file="")

        try:
            response = requests.get(url)
            response.raise_for_status()
        except Exception as ex:
            print("Failed to retrieve filelist from %s: %s" % (url, ex))
            continue

        files = link_regex.findall(response.text)
        break

    if not files:
        print("No files found!")
        return []

    out_data = []
    for file in files:
        file_match = build_group_regex.match(file)
        if file_match is None:
            print("Ignoring non nightly file '{}'".format(file))
            continue

        group_match = file_match.group(1)
        primary_url = None
        mirrors = []

        # x64 is the name Visual Studio uses but Win64 works better for us since that gets displayed in the nightly post
        if "x64" in group_match:
            group_match = group_match.replace("x64", "Win64")

        # nebula.py expects "MacOSX" as the group, but the build actions may pass off as just "Mac"
        if "Mac" == group_match:
            group_match = group_match.replace("Mac", "MacOSX")

        for mirror in config["ftp"]["mirrors"]:
            download_url = mirror.format(type="nightly", version=version_str, file=file)
            if primary_url is None:
                primary_url = download_url
            else:
                mirrors.append(download_url)

        out_data.append(ReleaseFile(file, primary_url, group_match, None, mirrors))

    return out_data
