import json
import os
import random
import requests
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from base64 import b64encode

from updater import main


class TestMain(unittest.TestCase):
    maxDiff = None
    web_server_port = random.randint(10000, 65535)
    # start web server in background
    web_server = subprocess.Popen(
        args=[
            f"{sys.executable}",  # absolute path to python
            "-m",
            "http.server",
            "--bind",
            "localhost",
            f"{web_server_port}",
        ],
    )
    main_directory = os.getcwd()

    @classmethod
    def setUpClass(cls) -> None:
        os.environ["GIT_HMRC_USER_API_TOKEN"] = get_git_hmrc_user_token()
        os.environ["GITHUB_API_TOKEN"] = get_git_readonly_user_token()
        # give web_server time to boot up
        time.sleep(0.5)

    def setUp(self) -> None:
        self.test_directory = tempfile.mkdtemp()
        copy_repo_to_test_dir(self)
        os.chdir(os.path.join(self.test_directory, "build-dynamic-application-security-testing"))
        configure_git()

    def setUpEnv(self, git_pr_title: str) -> None:
        self.original_pr_title = os.getenv("GIT_PR_TITLE")
        if git_pr_title is None:
            return
        os.environ["GIT_PR_TITLE"] = git_pr_title

    def test_function_success_for_four_addons(self) -> None:
        """
        Exercise complete flow for four usual addons if we call main function.
        """
        want_pr_title = unittest.TestCase.id(self)
        self.setUpEnv(git_pr_title=want_pr_title)

        addons_path = f"{os.getcwd()}/updater/test/resources/{unittest.TestCase.id(self)}.input.zap_addons"
        dockerfile_path = f"{os.getcwd()}/Dockerfile"
        xml_url = f"http://localhost:{self.web_server_port}/test/resources/{unittest.TestCase.id(self)}.input.xml"

        main(addons_path, dockerfile_path, xml_url, True)

        assert_repo_has_fork(self)
        assert_pull_request_is_from_fork(self)
        assert_pull_request_diff_equal(self)
        self.assertTrue(
            slack_notification_sent(want_pr_title),
            f"Expected Slack notification sent with title '{want_pr_title}' in message attachments",
        )

    def test_function_no_pull_request_created(self) -> None:
        """
        No pull request is created when no changes are made in the Dockerfile.
        """
        want_pr_title = unittest.TestCase.id(self)
        self.setUpEnv(git_pr_title=want_pr_title)

        addons_path = f"{os.getcwd()}/updater/test/resources/{unittest.TestCase.id(self)}.input.zap_addons"
        dockerfile_path = f"{os.getcwd()}/Dockerfile"
        xml_url = f"http://localhost:{self.web_server_port}/test/resources/{unittest.TestCase.id(self)}.input.xml"

        main(addons_path, dockerfile_path, xml_url, True)

        assert_repo_has_no_fork(self)
        assert_no_pull_request(self)
        self.assertFalse(
            slack_notification_sent(want_pr_title),
            f"Expected no Slack notification sent with title '{want_pr_title}' in message attachments",
        )

    def test_executable_success_for_four_addons(self) -> None:
        """
        Exercise complete flow for four usual addons if we call executable with arguments.
        """
        want_pr_title = unittest.TestCase.id(self)
        self.setUpEnv(git_pr_title=want_pr_title)

        addons_path = f"{os.getcwd()}/updater/test/resources/{unittest.TestCase.id(self)}.input.zap_addons"
        dockerfile_path = f"{os.getcwd()}/Dockerfile"
        xml_url = f"http://localhost:{self.web_server_port}/test/resources/{unittest.TestCase.id(self)}.input.xml"

        result = subprocess.run(
            args=[
                f"{self.main_directory}/updater.py",
                "--addons",
                addons_path,
                "--dockerfile",
                dockerfile_path,
                "--url",
                xml_url,
            ]
        )

        self.assertEqual(result.returncode, 0, "Expected the updater script to exit without error code")

        assert_repo_has_fork(self)
        assert_pull_request_is_from_fork(self)
        assert_pull_request_diff_equal(self)
        self.assertTrue(
            slack_notification_sent(want_pr_title),
            f"Expected Slack notification sent with title '{want_pr_title}' in message attachments",
        )

    def tearDown(self) -> None:
        delete_git_fork_and_repository()
        os.chdir(self.main_directory)
        shutil.rmtree(self.test_directory)
        if self.original_pr_title is not None:
            os.environ["GIT_PR_TITLE"] = self.original_pr_title

    @classmethod
    def tearDownClass(cls) -> None:
        # terminate web server and wait until it is done
        cls.web_server.terminate()
        cls.web_server.wait()
        run_command("make stop-git-server", "Could not stop git server")
        run_command("make stop-slack-service-stub", "Could not stop Slack server stub")


def get_git_hmrc_user_token() -> str:
    return get_git_token(os.environ["GIT_HMRC_USER"])


def get_git_readonly_user_token() -> str:
    return get_git_token(os.environ["GITHUB_API_USER"])


def get_git_token(user: str) -> str:
    basic_credentials = b64encode(f"{user}:{user}".encode("utf-8")).decode("utf-8")
    return str(
        requests.post(
            url=f"http://{os.getenv('GIT_HOST')}/api/v1/users/{user}/tokens",
            headers={
                "Content-Type": "application/json",
                "Accept": "accept: application/json",
                "Authorization": f"Basic {basic_credentials}",
            },
            json={"name": "token_name"},
        ).json()["sha1"]
    )


def update_file(test: TestMain, kind: str, extension: str, content: str) -> None:
    target_file = f"{test.main_directory}/test/resources/{unittest.TestCase.id(test)}.{kind}.{extension}"
    print(f"Updating {kind} file: {target_file}")
    with open(target_file, "w") as test_file:
        test_file.write(content)


def load_file(test: TestMain, kind: str, extension: str) -> str:
    with open(f"{os.getcwd()}/updater/test/resources/{unittest.TestCase.id(test)}.{kind}.{extension}") as target_file:
        return target_file.read()


def assert_repo_has_fork(self: TestMain) -> None:
    forks = requests.get(url=os.environ["GIT_API_FORK_URL"]).json()
    self.assertEqual(len(forks), 1, f"expected to find one fork but found {len(forks)}")

    fork_owner = forks[0]["owner"]["username"]
    self.assertEqual(fork_owner, os.getenv("GITHUB_API_USER"))

    fork_parent = forks[0]["parent"]["owner"]["username"]
    self.assertEqual(fork_parent, os.getenv("GIT_HMRC_USER"))


def assert_repo_has_no_fork(self: TestMain) -> None:
    forks = requests.get(url=os.environ["GIT_API_FORK_URL"]).json()
    self.assertEqual(len(forks), 0, f"expected no fork but found {len(forks)}")


def assert_pull_request_is_from_fork(self: TestMain) -> None:
    pulls = requests.get(url=os.environ["GIT_API_PR_URL"]).json()
    self.assertEqual(len(pulls), 1, f"expected to find one pull request but found {len(pulls)}")

    is_fork = pulls[0]["head"]["repo"]["fork"]
    self.assertTrue(is_fork, "expected the pull request to come from a fork but it doesn't")


def assert_pull_request_diff_equal(self: TestMain) -> None:
    got_diff = requests.get(f"{os.getenv('GIT_PR_URL')}/1.diff").text
    if os.getenv("UPDATE_GOLDEN_FILES"):
        update_file(self, "golden", "diff", got_diff)
        shutil.copyfile(
            f"{self.main_directory}/test/resources/{unittest.TestCase.id(self)}.golden.diff",
            f"{self.test_directory}/{unittest.TestCase.id(self)}.golden.diff",
        )

    self.assertEqual(got_diff.strip(), load_file(self, "golden", "diff").strip())


def assert_no_pull_request(self: TestMain) -> None:
    pull_requests = requests.get(url=os.environ["GIT_API_PR_URL"]).json()
    self.assertEqual(len(pull_requests), 0, "Expected no pull requests to be raised")


def slack_notification_sent(want_pr_title: str) -> bool:
    notifications = requests.get(f"http://{os.getenv('SLACK_HOST')}/__admin/requests").json()["requests"]

    for notification in notifications:
        blocks = json.loads(notification["request"]["body"])["blocks"]
        if want_pr_title in str(blocks):
            return True
    return False


def copy_repo_to_test_dir(test: TestMain) -> None:
    path = os.getcwd()
    rp = os.path.abspath(os.path.join(path, os.pardir))

    shutil.copytree(rp, os.path.join(test.test_directory, "build-dynamic-application-security-testing"))
    shutil.copy2(
        f"{test.main_directory}/test/resources/{unittest.TestCase.id(test)}.input.Dockerfile",
        os.path.join(test.test_directory, "build-dynamic-application-security-testing", "Dockerfile"),
    )


def configure_git_user(user: str, token: str) -> None:
    with open(f"{os.getenv('HOME')}/.git-credentials", "w") as file:
        file.write(f"http://{user}:{token}@{os.getenv('GIT_HOST')}")

    run_command("git config --global credential.helper store", "Could not configure git credential helper")
    run_command(f"git config --global user.name '{user}'", "Could not configure git user name")
    run_command(f"git config --global user.email '{user}'", "Could not configure git user email")


def configure_git() -> None:
    configure_git_user(os.environ["GIT_HMRC_USER"], os.environ["GIT_HMRC_USER_API_TOKEN"])
    requests.post(
        url=f"http://{os.environ['GIT_HOST']}/api/v1/user/repos",
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
            "authorization": f"token {os.getenv('GIT_HMRC_USER_API_TOKEN')}",
        },
        json={"default_branch": "main", "name": "build-dynamic-application-security-testing"},
    )
    run_command("git init --initial-branch main", "Could not initialise git repository")
    run_command(
        f"git remote add origin http://{os.getenv('GIT_HOST')}/{os.getenv('GIT_HMRC_USER')}/build-dynamic-application-security-testing.git",
        "Could not add git origin",
    )
    run_command("git stage .", "Could not stage files")
    run_command("git commit --message 'Initial commit'", "Could not make initial commit")
    run_command("git push --set-upstream origin main", "Could not push initial commit")

    configure_git_user(os.environ["GITHUB_API_USER"], os.environ["GITHUB_API_TOKEN"])


def delete_git_fork_and_repository() -> None:
    requests.delete(
        url=f"http://{os.getenv('GIT_HOST')}/api/v1/repos/{os.getenv('GITHUB_API_USER')}/build-dynamic-application-security-testing",
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
            "authorization": f"token {os.getenv('GITHUB_API_TOKEN')}",
        },
    )
    requests.delete(
        url=f"http://{os.getenv('GIT_HOST')}/api/v1/repos/{os.getenv('GIT_HMRC_USER')}/build-dynamic-application-security-testing",
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
            "authorization": f"token {os.getenv('GIT_HMRC_USER_API_TOKEN')}",
        },
    )


def run_command(cmd: str, err: str) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    if proc.returncode != 0:
        raise SystemExit(f"{err}: {proc.stdout.decode('utf-8')}")


if __name__ == "__main__":
    unittest.main()
