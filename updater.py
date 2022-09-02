#!/usr/bin/env python3

import argparse
import datetime
import logging
import os
import re
import requests
import shutil
import slack
import subprocess
import time
import xml.dom.minidom
from dataclasses import dataclass, field
from typing import Any, Dict, List


class CreateGitBranchException(Exception):
    pass


class CreatePullRequestException(Exception):
    pass


class CreateForkException(Exception):
    pass


class DeleteForkException(Exception):
    pass


class CloneForkException(Exception):
    pass


class CopyDockerfileToForkException(Exception):
    pass


class CommitChangesException(Exception):
    pass


class ForkNotFoundException(Exception):
    pass


class GetEnvException(Exception):
    pass


class PushChangesException(Exception):
    pass


class PostNotificationException(Exception):
    pass


class RecreateForkException(Exception):
    pass


def getenv_or_raise(env_name: str) -> str:
    env = os.getenv(env_name, "").strip()
    if not env:
        raise GetEnvException(f"{env_name} environment variable is not set")
    return env


@dataclass
class Dependency:
    """ZAP addon dependency state holder"""

    id: str
    version: str = ""


@dataclass
class Addon:
    """ZAP addon state holder"""

    name: str  # shortname used in addon XML tags
    date: str = ""  # release date
    file: str = ""
    hash: str = ""
    not_before_version: str = ""
    status: str = ""
    url: str = ""
    version: str = ""
    dependencies: List[Dependency] = field(default_factory=list)


@dataclass
class PullRequest:
    """Pull Request state holder"""

    title: str
    head: str
    body: str
    base: str = "main"
    api_create_url: str = os.getenv("GIT_API_PR_URL", "https://api.github.com/repos/hmrc/build-dynamic-application-security-testing/pulls")
    url: str = ""

    def payload(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "head": f"{getenv_or_raise('GITHUB_API_USER')}:{self.head}",
            "base": self.base,
            "body": self.body,
        }


def main(zap_addons_path: str, dockerfile_path: str, xml_url: str, publish: bool) -> None:
    logging.basicConfig(
        format="%(asctime)s %(filename)s | %(levelname)s | %(funcName)s | %(message)s",
        level=logging.WARNING,
    )
    addons = build_addons(zap_addons_path, xml_url)
    needs_publishing = write_dockerfile(addons, dockerfile_path)

    if needs_publishing & publish:
        pr = publish_changes(dockerfile_path, commit_message(addons))
        slack.Notifier("team-platops-alerts").send_info(":owasp-zap: ZAP addons update", pr.title, pr.url)


def publish_changes(dockerfile_path: str, pr_message: str) -> PullRequest:
    timestamp = datetime.datetime.now(datetime.timezone.utc)
    branch_name = f"zap_addons_update_{timestamp.strftime('%Y_%m_%d__%H_%M_%S_%Z')}"  # 2020_10_22__10_20_59_UTC
    title = f"ZAP addons auto update from {timestamp.strftime('%d %b %Y %H:%M %Z')}"  # 01 Jan 2020 02:05 UTC
    recreate_fork()
    fork_path = clone_fork()
    fork_dockerfile = copy_zap_dockerfile_into_fork(dockerfile_path=dockerfile_path, fork_path=fork_path)
    checkout_new_git_branch(branch_name)
    commit_changes(fork_dockerfile, "Auto update ZAP addons")
    push_changes(branch_name)
    return create_pull_request(title, branch_name, pr_message)


def recreate_fork(attempt: int = 0) -> None:
    """
    Fork names in GitHub are not predictable. Most likely forks are named after the parent repo's name.
    However, GitHub occasionally appends indices to fork names (e.g. "build-dynamic-application-security-testing-1").
    When this happens, the B&D PR Builder job in Jenkins doesn't trigger because of the name mismatch
    between fork and parent repos.
    Therefore, we make a few attempts at recreating the fork until its name is correct.
    """
    delete_fork()
    create_fork()
    if look_up_fork_name() == "build-dynamic-application-security-testing":
        return
    elif attempt >= 14:
        raise RecreateForkException()
    recreate_fork(attempt + 1)


def checkout_new_git_branch(branch_name: str) -> None:
    output = subprocess.run(
        args=["git", "checkout", "-b", branch_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if output.returncode != 0:
        raise CreateGitBranchException(
            f"failed to create and checkout branch {branch_name}: {output.stdout.decode('utf-8')}"
        )


def commit_changes(dockerfile_path: str, message: str) -> None:
    add_output = subprocess.run(
        args=["git", "add", dockerfile_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if add_output.returncode != 0:
        raise CommitChangesException(
            f"failed add {dockerfile_path} to git changes: {add_output.stdout.decode('utf-8')}"
        )

    commit_output = subprocess.run(
        args=["git", "commit", "--message", message],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if commit_output.returncode != 0:
        raise CommitChangesException(f"failed to commit Dockerfile changes: {commit_output.stdout.decode('utf-8')}")


def push_changes(branch_name: str) -> None:
    output = subprocess.run(
        args=["git", "push", "--set-upstream", "origin", branch_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if output.returncode != 0:
        raise PushChangesException(f"failed to push Dockerfile changes: {output.stdout.decode('utf-8')}")


def build_github_headers() -> Dict[str, str]:
    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {getenv_or_raise('GITHUB_API_TOKEN')}",
        "Content-Type": "application/json",
    }


def create_pull_request(title: str, head: str, body: str) -> PullRequest:
    pull_request = PullRequest(title=os.getenv("GIT_PR_TITLE", title), head=head, body=body)
    try:
        response = requests.post(
            url=pull_request.api_create_url, headers=build_github_headers(), json=pull_request.payload()
        )
        response.raise_for_status()
        pull_request.url = response.json()["html_url"]
        return pull_request
    except requests.RequestException as err:
        raise CreatePullRequestException(
            f"cannot send request to {pull_request.api_create_url} " f"with payload: {pull_request.payload()}"
        ) from err


def delete_fork() -> None:
    if not fork_exists():
        return

    fork_name = look_up_fork_name()
    fork_repo_url = os.getenv("GIT_FORK_URL", f"https://api.github.com/repos/hmrc-read-only/{fork_name}")
    try:
        requests.delete(url=fork_repo_url, headers=build_github_headers()).raise_for_status()
        logging.info(f"fork {fork_name} has been deleted")
    except requests.RequestException as err:
        raise DeleteForkException(f"cannot delete fork '{fork_repo_url}': {err}") from err


def create_fork() -> None:
    """
    From https://docs.github.com/en/free-pro-team@latest/rest/reference/repos#create-a-fork
    Forking a Repository happens asynchronously. You may have to wait a short period of time before you can access
    the git objects. It shouldn't take longer than 5 minutes.
    """
    create_fork_url = os.getenv("GIT_API_FORK_URL", "https://api.github.com/repos/hmrc/build-dynamic-application-security-testing/forks")
    try:
        requests.post(url=create_fork_url, headers=build_github_headers()).raise_for_status()
        for attempt in range(15):
            if fork_exists():
                return
            logging.debug(f"fork not created yet, will check again in an instant (attempt #{attempt})")
            time.sleep(float(os.getenv("RETRY_DELAY", 20)))
        raise CreateForkException("fork took too long to create, aborting")
    except requests.RequestException as err:
        raise CreateForkException(f"cannot create fork: {err}") from err


def get_fork() -> Dict[Any, Any]:
    list_forks_url = os.getenv("GIT_API_FORK_URL", "https://api.github.com/repos/hmrc/build-dynamic-application-security-testing/forks")
    forks = requests.get(url=list_forks_url, headers=build_github_headers()).json()
    filtered_forks = filter(lambda fork: fork["owner"]["login"] == getenv_or_raise("GITHUB_API_USER"), forks)
    try:
        return dict(next(filtered_forks))
    except StopIteration:
        raise ForkNotFoundException()


def fork_exists() -> bool:
    try:
        get_fork()
        return True
    except ForkNotFoundException:
        return False


def look_up_fork_name() -> str:
    return str(get_fork()["name"])


def clone_fork() -> str:
    github_user = getenv_or_raise("GITHUB_API_USER")
    github_token = getenv_or_raise("GITHUB_API_TOKEN")
    fork_name = look_up_fork_name()
    fork_url = os.getenv("GIT_FORK_URL", f"https://{github_user}:{github_token}@github.com/hmrc-read-only/{fork_name}")
    fork_dir = os.path.join(os.getcwd(), "fork")
    output = subprocess.run(
        args=["git", "clone", fork_url, fork_dir],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if output.returncode != 0:
        raise CloneForkException(f"failed to clone fork repository '{fork_url}': {output.stdout.decode('utf-8')}")
    return fork_dir


def copy_zap_dockerfile_into_fork(dockerfile_path: str, fork_path: str) -> str:
    dest = os.path.join(fork_path, "docker", os.path.basename(dockerfile_path))
    try:
        os.chdir(fork_path)
        shutil.copyfile(dockerfile_path, dest)
        return dest
    except shutil.Error as err:
        raise CopyDockerfileToForkException(
            f"cannot copy Dockerfile '{dockerfile_path}' into fork repo dir '{dest}'"
        ) from err


def build_addons(zap_addons_path: str, xml_url: str) -> List[Addon]:
    return fill_addons_details(read_addons(zap_addons_path), fetch_addons_xml(xml_url))


def write_dockerfile(addons: List[Addon], dockerfile_path: str) -> bool:
    dockerfile_block = generate_dockerfile_block(addons)
    dockerfile_content = load_dockerfile(dockerfile_path)

    needs_updating = dockerfile_block not in dockerfile_content

    if needs_updating:
        dockerfile_content = update_dockerfile(dockerfile_content, dockerfile_block)
        save_dockerfile(dockerfile_path, dockerfile_content)

    return needs_updating


def read_addons(file_path: str) -> List[Addon]:
    with open(file_path) as file:
        addon_names = file.read().splitlines()

    addons: List[Addon] = []
    for addon_name in addon_names:
        if addon_name != "":
            addons.append(Addon(addon_name))
    return addons


def fetch_addons_xml(url: str) -> str:
    return requests.get(url).text


# Use Addon name to find its XML node with Addon details and add them to each
# Addon object
def fill_addons_details(addons: List[Addon], xml_string: str) -> List[Addon]:
    # ZAP tree in XML
    zap = xml.dom.minidom.parseString(xml_string)
    dependencies: List[Addon] = []
    for addon in addons:
        transitive_addon_tag = "addon_" + addon.name
        try:
            xml_addon = zap.getElementsByTagName(transitive_addon_tag)[0]
        except IndexError:
            addons.remove(addon)
            logging.warning(f"cannot find XML tag: {transitive_addon_tag}, removing it from update")
            continue

        addon.date = read_tag_value(xml_addon, "date")
        addon.file = read_tag_value(xml_addon, "file")
        addon.hash = read_tag_value(xml_addon, "hash")
        addon.not_before_version = read_tag_value(xml_addon, "not-before-version")
        addon.status = read_tag_value(xml_addon, "status")
        addon.url = read_tag_value(xml_addon, "url")
        addon.version = read_tag_value(xml_addon, "version")
        try:
            transitive_addons_list_tag = (
                xml_addon.getElementsByTagName("dependencies")[0]
                .getElementsByTagName("addons")[0]
                .getElementsByTagName("addon")
            )
        except IndexError:
            logging.info(f"addon {addon.name} does not have transitive dependencies")
            continue

        for transitive_addon_tag in transitive_addons_list_tag:
            dependency_name = read_tag_value(transitive_addon_tag, "id")
            dependency_version = read_tag_value(transitive_addon_tag, "version")
            addon.dependencies.append(Dependency(id=dependency_name, version=dependency_version))
            add_if_not_exists(dependencies, dependency_name, xml_string)

    addons.extend(dependencies)

    return addons


def add_if_not_exists(addons: List[Addon], dependency_name: str, xml_string: str) -> None:
    if not next((x for x in addons if x.name == dependency_name), None):
        addons.extend(fill_addons_details([Addon(name=dependency_name)], xml_string))


def read_tag_value(xml_tag: xml.dom.minidom.Node, tag: str) -> str:
    try:
        return str(xml_tag.getElementsByTagName(tag)[0].childNodes[0].data)
    except IndexError:
        logging.info(f"tag {tag} does not exist")

    return ""


def generate_dockerfile_block(addons: List[Addon]) -> str:
    if len(addons) == 0:
        return ""

    args_lines = ""
    rm_lines = ""
    wget_lines = ""
    max_index = len(addons) - 1
    for index, addon in enumerate(addons):
        args_lines += f"ARG {addon.name.upper()}_VERSION={addon.version}"
        rm_lines += f"        {addon.name}-{addon.status}-*.zap \\"
        version_string = f"${{{addon.name.upper()}_VERSION}}"
        wget_lines += f"        {addon.url.replace(str(addon.version),version_string)}"
        if index < max_index:
            args_lines += "\n"
            rm_lines += "\n"
            wget_lines += " \\\n"

    return f"""
WORKDIR /zap/plugin
{args_lines}
RUN rm --force \\
{rm_lines}
    && wget --quiet \\
{wget_lines}
"""


def load_dockerfile(dockerfile_path: str) -> str:
    with open(dockerfile_path) as dockerfile_file:
        dockerfile_content = dockerfile_file.read()
    return dockerfile_content


def update_dockerfile(dockerfile_content: str, dockerfile_block: str) -> str:
    autogenerated_start = "# Autogenerated by updater.py - DO NOT EDIT MANUALLY"
    autogenerated_end = "# Autogenerated END"
    if not dockerfile_block.endswith("\n"):
        dockerfile_block += "\n"
    return re.sub(
        f"{autogenerated_start}.*{autogenerated_end}",
        f"{autogenerated_start}{dockerfile_block}{autogenerated_end}",
        dockerfile_content,
        flags=re.DOTALL,  # '.' will also match newlines
    )


def save_dockerfile(dockerfile_path: str, dockerfile_content: str) -> None:
    with open(dockerfile_path, "w") as dockerfile_file:
        dockerfile_file.write(dockerfile_content)
    return


def commit_message(addons: List[Addon]) -> str:
    if len(addons) == 0:
        return ""

    addons_info = ""
    for addon in addons:
        addons_info += (
            f"- {addon.name}:\n"
            f"  - version: {addon.version}\n"
            f"  - status: {addon.status}\n"
            f"  - released: {addon.date}\n"
        )

    return f"Update ZAP addons from upstream\n\n{addons_info}"


def get_zap_version(version_file_path: str) -> str:
    with open(version_file_path) as version_file:
        version_line = version_file.readline()
    version = version_line.strip().split(".")
    return f"{version[0]}.{version[1]}"  # major.minor


if __name__ == "__main__":
    # get absolute path to this script for walking this repo
    script_directory = os.path.dirname(os.path.abspath(__file__))
    zap_addons_path = os.path.normpath(os.path.join(script_directory, "zap_addons"))
    dockerfile_path = os.path.normpath(os.path.join(script_directory, "Dockerfile"))
    zap_version = get_zap_version(os.path.normpath(os.path.join(script_directory, ".zap-version")))
    xml_url = f"https://raw.githubusercontent.com/zaproxy/zap-admin/master/ZapVersions-{zap_version}.xml"

    parser = argparse.ArgumentParser(description="Update ZAP Addons in Dockerfile.")
    parser.add_argument(
        "-a",
        "--addons",
        type=str,
        default=zap_addons_path,
        help="path to file which lists all required addons",
    )
    parser.add_argument(
        "-d",
        "--dockerfile",
        type=str,
        default=dockerfile_path,
        help="path to ZAP Dockerfile",
    )
    parser.add_argument(
        "-u",
        "--url",
        type=str,
        default=xml_url,
        help="URL to XML documents which lists ZAP addons",
    )
    parser.add_argument(
        "--no-publish",
        action="store_false",
        help="do not create a PR of the changes",
    )

    args = parser.parse_args()
    main(args.addons, args.dockerfile, args.url, args.no_publish)
