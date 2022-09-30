import dataclasses
import json
import os
import subprocess
import shutil
import tempfile
import unittest
from requests import RequestException
from shutil import copyfile
from typing import List
from unittest.mock import Mock, call, mock_open, patch

import httpretty

from updater import (
    Addon,
    CommitChangesException,
    CreateGitBranchException,
    CreatePullRequestException,
    CreateForkException,
    DeleteForkException,
    CloneForkException,
    CopyDockerfileToForkException,
    RecreateForkException,
    Dependency,
    ForkNotFoundException,
    GetEnvException,
    PullRequest,
    PushChangesException,
    checkout_new_git_branch,
    commit_changes,
    commit_message,
    create_pull_request,
    create_fork,
    delete_fork,
    clone_fork,
    recreate_fork,
    get_fork,
    fork_exists,
    look_up_fork_name,
    copy_zap_dockerfile_into_fork,
    fetch_addons_xml,
    fill_addons_details,
    generate_dockerfile_block,
    getenv_or_raise,
    get_zap_version,
    load_dockerfile,
    push_changes,
    read_addons,
    save_dockerfile,
    update_dockerfile,
    write_dockerfile,
)


def update_file_addons(test: unittest.TestCase, kind: str, got_addons: List[Addon]) -> None:
    target_file = f"test/resources/{unittest.TestCase.id(test)}.{kind}.json"

    # Build JSON from addons by converting Addon objects to dictionaries
    json_input = []
    for addon in got_addons:
        json_input.append(dataclasses.asdict(addon))

    print(f"Updating {kind} file: {target_file}")
    with open(target_file, "w") as test_file:
        json.dump(json_input, test_file, indent=2)


def load_file_addons(test: unittest.TestCase, kind: str) -> List[Addon]:
    with open(f"test/resources/{unittest.TestCase.id(test)}.{kind}.json") as target_file:
        raw_json = json.load(target_file)

    # Convert dictionaries to Addon objects
    addons = []  # type: List[Addon]
    for addon_dict in raw_json:
        for index, dependency_dict in enumerate(addon_dict["dependencies"]):
            addon_dict["dependencies"][index] = Dependency(**dependency_dict)
        addon = Addon(**addon_dict)
        addons.append(addon)

    return addons


def update_file(test: unittest.TestCase, kind: str, extension: str, content: str) -> None:
    target_file = f"test/resources/{unittest.TestCase.id(test)}.{kind}.{extension}"
    print(f"Updating {kind} file: {target_file}")
    with open(target_file, "w") as test_file:
        test_file.write(content)


def load_file(test: unittest.TestCase, kind: str, extension: str) -> str:
    with open(f"test/resources/{unittest.TestCase.id(test)}.{kind}.{extension}") as target_file:
        content = target_file.read()

    return content


class TestReadAddons(unittest.TestCase):
    maxDiff = None

    def test_one_addon(self) -> None:
        """
        Try only one addon in input file.
        """
        # create tempfile with content to use for read_addon
        with tempfile.NamedTemporaryFile() as temp:
            temp.write(b"ascanrules-release")
            temp.flush()

            want = [Addon(name="ascanrules-release")]
            got = read_addons(temp.name)

        self.assertEqual(got, want)

    def test_two_addons(self) -> None:
        """
        Try this with two addons.
        """
        # create tempfile with content to use for read_addon
        with tempfile.NamedTemporaryFile() as temp:
            temp.write(b"ascanrules-release\nascanrulesBeta-beta\n")
            temp.flush()

            want = [Addon(name="ascanrules-release"), Addon(name="ascanrulesBeta-beta")]
            got = read_addons(temp.name)

        self.assertEqual(got, want)

    def test_two_addons_with_CRLF(self) -> None:
        """
        Check that Windows style new lines are not breaking functionality.
        """
        # create tempfile with content to use for read_addon
        with tempfile.NamedTemporaryFile() as temp:
            temp.write(b"ascanrules-release\r\nascanrulesBeta-beta\r\n")
            temp.flush()

            want = [Addon(name="ascanrules-release"), Addon(name="ascanrulesBeta-beta")]
            got = read_addons(temp.name)

        self.assertEqual(got, want)

    def test_empty_line_wont_create_addon(self) -> None:
        """
        Empty lines should not create empty Addon objects.
        """
        # create tempfile with content to use for read_addon
        with tempfile.NamedTemporaryFile() as temp:
            temp.write(b"\n\r\n\n")
            temp.flush()

            want: List[Addon] = []
            got = read_addons(temp.name)

        self.assertEqual(got, want)


class TestFetchAddonsXML(unittest.TestCase):
    @httpretty.activate
    def test_xml_string_return(self) -> None:
        """
        Get XML string from given URL.
        """
        source = "<ZAP>dast</ZAP>"
        url = "https://path.to/file.xml"

        httpretty.register_uri(method=httpretty.GET, uri=url, body=source)

        got = fetch_addons_xml(url)
        self.assertEqual(got, source)


class TestFillAddonsDetails(unittest.TestCase):
    maxDiff = None

    def test_return_empty_if_no_addons_passed(self) -> None:
        """
        Return empty list from correct XML file if no addons are passed.
        """
        xml_path = "test/resources/zap_addon_versions.xml"
        addons: List[Addon] = []

        with open(xml_path) as xml_file:
            xml_string = xml_file.read()

        self.got = fill_addons_details(addons, xml_string)
        want = load_file_addons(self, "golden")

        self.assertEqual(self.got, want)

    def test_filling_one_addon(self) -> None:
        """
        Fill all details from correct XML file for one passed valid addon.
        """
        xml_path = "test/resources/zap_addon_versions.xml"
        addons = [Addon(name="ascanrules")]

        with open(xml_path) as xml_file:
            xml_string = xml_file.read()

        self.got = fill_addons_details(addons, xml_string)
        want = load_file_addons(self, "golden")

        self.assertEqual(self.got, want)

    def test_filling_two_addons(self) -> None:
        """
        Fill all details from correct XML file for two passed valid addon.
        """
        xml_path = "test/resources/zap_addon_versions.xml"
        addons = [Addon(name="ascanrules"), Addon(name="ascanrulesBeta")]

        with open(xml_path) as xml_file:
            xml_string = xml_file.read()

        self.got = fill_addons_details(addons, xml_string)
        want = load_file_addons(self, "golden")

        self.assertEqual(self.got, want)

    def test_filling_one_valid_and_one_invalid_addon(self) -> None:
        """
        Fill all details from correct XML file for one addon and drop records
        about addon that cannot be found in XML.
        """
        xml_path = "test/resources/zap_addon_versions.xml"
        addons = [Addon(name="ascanrules"), Addon(name="notValidPluginName")]

        with open(xml_path) as xml_file:
            xml_string = xml_file.read()

        self.got = fill_addons_details(addons, xml_string)
        want = load_file_addons(self, "golden")

        self.assertEqual(self.got, want)

    def test_filling_one_addon_with_dependency_and_attach_it_to_list(self) -> None:
        """
        Fill all details from correct XML file for one passed valid addon that
        has dependency and add that dependency as an addon to the original list
        of addons.
        """
        xml_path = "test/resources/zap_addon_versions.xml"
        addons = [Addon(name="pscanrules")]

        with open(xml_path) as xml_file:
            xml_string = xml_file.read()

        self.got = fill_addons_details(addons, xml_string)
        want = load_file_addons(self, "golden")

        self.assertEqual(self.got, want)

    def test_filling_one_addon_with_dependency_and_version_and_attach_it_to_list(self) -> None:
        """
        Fill all details from correct XML file for one passed valid addon that
        has dependency (with version) and add that dependency as an addon to the
        original list of addons.
        """
        xml_path = "test/resources/zap_addon_versions.xml"
        addons = [Addon(name="domxss")]

        with open(xml_path) as xml_file:
            xml_string = xml_file.read()

        self.got = fill_addons_details(addons, xml_string)
        want = load_file_addons(self, "golden")

        self.assertEqual(self.got, want)

    def tearDown(self) -> None:
        if os.getenv("UPDATE_GOLDEN_FILES"):
            update_file_addons(self, "golden", self.got)


class TestGenerateDockerfileBlock(unittest.TestCase):
    maxDiff = None

    def test_generate_valid_block_for_one_addon(self) -> None:
        """
        Generate valid Dockerfile block for one addon.
        """
        addons = load_file_addons(self, "input")

        self.got = generate_dockerfile_block(addons)
        want = load_file(self, "golden", "Dockerfile")

        self.assertEqual(self.got, want)

    def test_generate_valid_block_for_two_addons(self) -> None:
        """
        Generate valid Dockerfile block for two addons.
        """
        addons = load_file_addons(self, "input")

        self.got = generate_dockerfile_block(addons)
        want = load_file(self, "golden", "Dockerfile")

        self.assertEqual(self.got, want)

    def test_generate_valid_block_if_no_addon_is_given(self) -> None:
        """
        Generate valid Dockerfile if no addon is given. We should not break
        Dockerfile if we do not want modify current addons in source Docker
        image.
        """
        addons = load_file_addons(self, "input")

        self.got = generate_dockerfile_block(addons)
        want = load_file(self, "golden", "Dockerfile")

        self.assertEqual(self.got, want)

    def tearDown(self) -> None:
        if os.getenv("UPDATE_GOLDEN_FILES"):
            update_file(self, "golden", "Dockerfile", self.got)


class TestLoadDockerfile(unittest.TestCase):
    def test_dockerfile_string_return(self) -> None:
        """
        Exercise loading Dockerfile from file and returning its content.
        """
        want = "FROM owasp/zap2docker-stable:2.9.0"

        mock_data = mock_open(read_data=want)
        with patch("updater.open", mock_data):
            got = load_dockerfile("/path/to/Dockerfile")
            self.assertEqual(got, want)


class TestUpdateDockerfile(unittest.TestCase):
    maxDiff = None

    def test_generate_real_dockerfile_from_real_inputs(self) -> None:
        """
        Generate real valid Dockerfile from real valid inputs.
        """
        dockerfile_content = load_file(self, "input_content", "Dockerfile")
        dockerfile_block = load_file(self, "input_block", "Dockerfile")

        self.got = update_dockerfile(dockerfile_content, dockerfile_block)
        want = load_file(self, "golden", "Dockerfile")

        self.assertEqual(self.got, want)

    def test_generate_valid_dockerfile_for_new_empty_block(self) -> None:
        """
        Generate valid Dockerfile if Dockerfile block we are replacing is empty.
        """
        dockerfile_content = load_file(self, "input_content", "Dockerfile")
        dockerfile_block = load_file(self, "input_block", "Dockerfile")

        self.got = update_dockerfile(dockerfile_content, dockerfile_block)
        want = load_file(self, "golden", "Dockerfile")

        self.assertEqual(self.got, want)

    def test_generate_valid_dockerfile_for_old_empty_block(self) -> None:
        """
        Generate valid Dockerfile if new Dockerfile block is empty.
        """
        dockerfile_content = load_file(self, "input_content", "Dockerfile")
        dockerfile_block = load_file(self, "input_block", "Dockerfile")

        self.got = update_dockerfile(dockerfile_content, dockerfile_block)
        want = load_file(self, "golden", "Dockerfile")

        self.assertEqual(self.got, want)

    def tearDown(self) -> None:
        if os.getenv("UPDATE_GOLDEN_FILES"):
            update_file(self, "golden", "Dockerfile", self.got)


class TestSaveDockerfile(unittest.TestCase):
    def test_dockerfile_content_is_saved(self) -> None:
        """
        Exercise saving Dockerfile content to given file.
        """
        dockerfile_path = "/path/to/Dockerfile"
        dockerfile_content = "FROM owasp/zap2docker-stable:2.9.0"

        mock = mock_open()
        with patch("updater.open", mock):
            save_dockerfile(dockerfile_path, dockerfile_content)

        # Assert side-effects of saving given content to given file
        mock.assert_called_with(dockerfile_path, "w")
        mock().write.assert_called_with(dockerfile_content)


class TestCommitMessage(unittest.TestCase):
    maxDiff = None

    def test_return_message_for_one_addon(self) -> None:
        """
        Return properly formatted message for one addon.
        """
        addons = load_file_addons(self, "input")

        self.got = commit_message(addons)
        want = load_file(self, "golden", "txt")

        self.assertEqual(self.got, want)

    def test_return_message_for_two_addons(self) -> None:
        """
        Return properly formatted message for two addons.
        """
        addons = load_file_addons(self, "input")

        self.got = commit_message(addons)
        want = load_file(self, "golden", "txt")

        self.assertEqual(self.got, want)

    def test_return_empty_message_for_empty_addons(self) -> None:
        """
        Return properly formatted message for two addons.
        """
        addons: List[Addon] = []

        self.got = commit_message(addons)
        want = load_file(self, "golden", "txt")

        self.assertEqual(self.got, want)

    def tearDown(self) -> None:
        if os.getenv("UPDATE_GOLDEN_FILES"):
            update_file(self, "golden", "txt", self.got)


class TestGetZapVersion(unittest.TestCase):
    def test_return_correct_major_minor_version(self) -> None:
        """
        Return correct major.minor version of ZAP
        """
        input = "2.9.0"
        want = "2.9"

        mock_data = mock_open(read_data=input)
        with patch("updater.open", mock_data):
            got = get_zap_version("/path/to/.zap-version")
            self.assertEqual(got, want)

    def test_return_correct_major_minor_version_for_nasty_formmated_input(self) -> None:
        """
        Return correct major.minor version of ZAP if input is badly formatted
        but still contains version on the first line.
        """
        input = "\t 2.9.0\nI like to see world in flames\r\n"
        want = "2.9"

        mock_data = mock_open(read_data=input)
        with patch("updater.open", mock_data):
            got = get_zap_version("/path/to/.zap-version")
            self.assertEqual(got, want)


class TestCheckoutNewGitBranch(unittest.TestCase):
    def test_successfully_checkout_and_create_new_git_branch(self) -> None:
        """
        Successfully create new Git branch and checkout
        """
        branch_name = "update-zap-addons"
        want_args = ["git", "checkout", "-b", branch_name]

        mock_run = Mock()
        mock_run.return_value = subprocess.CompletedProcess(args=want_args, returncode=0)

        try:
            with patch("subprocess.run", mock_run):
                checkout_new_git_branch(branch_name)
        except CreateGitBranchException as err:
            self.fail(f"Exception should not be raised, but got:{err}")
        mock_run.assert_called_once_with(args=want_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_can_not_create_and_checkout_new_git_branch(self) -> None:
        """
        Create and checkout a new git branch fails
        """
        branch_name = "update-zap-addons"
        want_args = ["git", "checkout", "-b", branch_name]

        mock_run = Mock()
        mock_run.return_value = subprocess.CompletedProcess(
            args=want_args,
            returncode=128,
            stdout=(f"fatal: A branch named '{branch_name}' already exists.").encode("utf-8"),
        )

        with patch("subprocess.run", mock_run):
            with self.assertRaises(CreateGitBranchException):
                checkout_new_git_branch(branch_name)


class TestWriteDockerfile(unittest.TestCase):
    def setUp(self) -> None:
        # create copy of input Dockerfile as this one needs to be modified
        # during test
        copyfile(
            f"test/resources/{unittest.TestCase.id(self)}.input.Dockerfile",
            f"test/resources/{unittest.TestCase.id(self)}.test.Dockerfile",
        )

    def test_write_dockerfile_when_content_is_updated(self) -> None:
        """
        Dockerfile is written when auto-generated plugins block has changed.
        """
        addons = load_file_addons(self, "input")
        dockerfile_path = f"test/resources/{unittest.TestCase.id(self)}.test.Dockerfile"

        is_written = write_dockerfile(addons, dockerfile_path)

        got = load_file(self, "test", "Dockerfile")

        if os.getenv("UPDATE_GOLDEN_FILES"):
            update_file(self, "golden", "Dockerfile", got)
        want = load_file(self, "golden", "Dockerfile")

        self.assertEqual(got, want)
        self.assertTrue(is_written, "Dockerfile should have been written but wasn't")

    def test_dockerfile_is_not_written_when_content_has_not_changed(self) -> None:
        """
        Dockerfile is not written when auto-generated plugins block has not changed.
        """
        addons = load_file_addons(self, "input")
        dockerfile_path = f"test/resources/{unittest.TestCase.id(self)}.test.Dockerfile"

        is_written = write_dockerfile(addons, dockerfile_path)

        got = load_file(self, "test", "Dockerfile")

        if os.getenv("UPDATE_GOLDEN_FILES"):
            update_file(self, "golden", "Dockerfile", got)
        want = load_file(self, "golden", "Dockerfile")

        self.assertEqual(got, want)
        self.assertFalse(is_written, "Dockerfile should not have been written")


class TestCommitChanges(unittest.TestCase):
    def test_successfully_commit_zap_addons_updates(self) -> None:
        """
        Commit changed Dockerfile with ZAP Addons updates
        """
        dockerfile_path = "docker/Dockerfile"
        message = "some message"
        want_add_args = ["git", "add", dockerfile_path]
        want_commit_args = ["git", "commit", "--message", message]

        mock_run = Mock()
        mock_run.return_value = subprocess.CompletedProcess(args=want_add_args, returncode=0)

        try:
            with patch("subprocess.run", mock_run):
                commit_changes(dockerfile_path, message)
        except CommitChangesException as err:
            self.fail(f"Exception should not be raised, but got:{err}")
        mock_run.assert_has_calls(
            [
                call(args=want_add_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT),
                call(args=want_commit_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT),
            ]
        )

    def test_raising_exception_if_add_fails(self) -> None:
        """
        Try to add Dockerfile using git and fail with an exception
        """
        dockerfile_path = "docker/Dockerfile"
        message = "some message"
        want_add_args = ["git", "add", dockerfile_path]
        want_commit_args = ["git", "commit", "--message", message]

        mock_run = Mock()
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=want_add_args,
                returncode=128,
                stdout=(f"fatal: pathspec '{dockerfile_path}' did not match any files").encode("utf-8"),
            ),
            subprocess.CompletedProcess(args=want_commit_args, returncode=0),
        ]

        with patch("subprocess.run", mock_run):
            with self.assertRaises(CommitChangesException):
                commit_changes(dockerfile_path, message)

    def test_raising_exception_if_commit_fails(self) -> None:
        """
        Try to commit Dockerfile using git and fail with an exception
        """
        dockerfile_path = "docker/Dockerfile"
        message = "some message"

        want_add_args = ["git", "add", dockerfile_path]
        want_commit_args = ["git", "commit", "--message", message]

        mock_run = Mock()
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=want_add_args, returncode=0),
            subprocess.CompletedProcess(
                args=want_commit_args,
                returncode=128,
                stdout=("fatal: not a git repository (or any of the parent directories): .git").encode("utf-8"),
            ),
        ]

        with patch("subprocess.run", mock_run):
            with self.assertRaises(CommitChangesException):
                commit_changes(dockerfile_path, message)


class TestPushChanges(unittest.TestCase):
    def test_successfully_pushing_git_changes_to_origin(self) -> None:
        """
        Successfully push git changes to origin
        """
        branch_name = "update-zap-addons"
        want_args = ["git", "push", "--set-upstream", "origin", branch_name]

        mock_run = Mock()
        mock_run.return_value = subprocess.CompletedProcess(args=want_args, returncode=0)

        try:
            with patch("subprocess.run", mock_run):
                push_changes(branch_name)
        except PushChangesException as err:
            self.fail(f"Exception should not be raised, but got:{err}")
        mock_run.assert_called_once_with(args=want_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_can_not_push_git_changes(self) -> None:
        """
        Fail to push git changes
        """
        branch_name = "update-zap-addons"
        want_args = ["git", "push", "--set-upstream", "origin", branch_name]

        mock_run = Mock()
        mock_run.return_value = subprocess.CompletedProcess(
            args=want_args,
            returncode=1,
            stdout="error: failed to push some refs to 'github.com:hmrc/build-dynamic-application-security-testing.git'".encode(
                "utf-8"
            ),
        )

        with patch("subprocess.run", mock_run):
            with self.assertRaises(PushChangesException):
                push_changes(branch_name)


class TestCreatePullRequest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        os.environ["GITHUB_API_TOKEN"] = "token 1234567890"

    @httpretty.activate
    def test_successfully_create_pull_request(self) -> None:
        """
        Successfully create pull request in GitHub
        """
        want_pull_request = PullRequest(
            title="Title",
            body="pull request body",
            head="update-zap-addons",
            url="https://github.com/hrmc/build-dynamic-application-security-testing/pull/42",
        )
        want_req_headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {os.environ['GITHUB_API_TOKEN']}",
            "Content-Type": "application/json",
        }
        want_req_body = {
            "title": "Title",
            "head": "zap24:update-zap-addons",
            "base": "main",
            "body": "pull request body",
        }

        httpretty.register_uri(
            httpretty.POST,
            want_pull_request.api_create_url,
            body=json.dumps({"html_url": want_pull_request.url}),
            status=201,
        )
        try:
            got_pull_request = create_pull_request(
                want_pull_request.title, want_pull_request.head, want_pull_request.body
            )
        except CreatePullRequestException as err:
            self.fail(f"Exception should not be raised, but got:{err}")

        got_accept_header = str(httpretty.last_request().headers["Accept"])
        got_authorization_header = str(httpretty.last_request().headers["Authorization"])
        got_content_type_header = str(httpretty.last_request().headers["Content-Type"])

        got_req_body = httpretty.last_request().body

        self.assertEqual(got_accept_header, want_req_headers["Accept"])
        self.assertEqual(got_authorization_header, want_req_headers["Authorization"])
        self.assertEqual(got_content_type_header, want_req_headers["Content-Type"])
        self.assertEqual(json.loads(got_req_body), want_req_body)
        self.assertEqual(got_pull_request, want_pull_request)

    @httpretty.activate
    def test_fail_with_404_from_github(self) -> None:
        """
        Successfully create pull request in GitHub
        """
        pull_request = PullRequest(
            title="Title",
            head="update-zap-addons",
            base="main",
            body="Our detailed message.",
        )

        httpretty.register_uri(
            httpretty.POST,
            pull_request.api_create_url,
            body=json.dumps(
                {
                    "message": "Not Found",
                    "documentation_url": "https://developer.github.com/v3/pulls/#create-a-pull-request",
                }
            ),
            status=404,
        )
        with self.assertRaises(CreatePullRequestException):
            create_pull_request(pull_request.title, pull_request.head, pull_request.body)


class TestLookUpForkName(unittest.TestCase):
    @httpretty.activate
    def test_successfully_look_up_fork_name(self) -> None:
        want_fork_name = "some-fork-name-1"
        fork = {
            "name": want_fork_name,
            "owner": {"login": "hmrc-read-only"},
        }

        with patch("updater.get_fork", return_value=fork):
            self.assertEqual(look_up_fork_name(), want_fork_name)

    @httpretty.activate
    def test_look_up_fork_name_failure(self) -> None:
        with patch("updater.get_fork", side_effect=ForkNotFoundException):
            with self.assertRaises(ForkNotFoundException):
                look_up_fork_name()


class TestDeleteFork(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["GITHUB_API_TOKEN"] = "token 1234567890"

    @httpretty.activate
    def test_successfully_delete_fork(self) -> None:
        """
        Successfully delete fork repository in GitHub
        """
        want_req_headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": "token some_token",
            "Content-Type": "application/json",
        }
        fork_name = "some-fork-name"

        with patch("updater.fork_exists", return_value=True):
            with patch("updater.look_up_fork_name", return_value=fork_name):
                with patch.dict(
                    os.environ, {"GITHUB_API_USER": "some_username", "GITHUB_API_TOKEN": "some_token"}, clear=True
                ):
                    httpretty.register_uri(
                        httpretty.DELETE,
                        f"https://api.github.com/repos/hmrc-read-only/{fork_name}",
                        status=204,
                    )
                    httpretty.register_uri(
                        httpretty.GET,
                        "https://api.github.com/repos/hmrc/build-dynamic-application-security-testing/forks",
                        body=json.dumps([]),
                        status=200,
                    )
                    delete_fork()

        got_accept_header = str(httpretty.last_request().headers["Accept"])
        got_authorization_header = str(httpretty.last_request().headers["Authorization"])
        got_content_type_header = str(httpretty.last_request().headers["Content-Type"])

        self.assertEqual(got_accept_header, want_req_headers["Accept"])
        self.assertEqual(got_authorization_header, want_req_headers["Authorization"])
        self.assertEqual(got_content_type_header, want_req_headers["Content-Type"])

        self.assertEqual(1, len(httpretty.latest_requests()))

        delete_fork_request = httpretty.latest_requests()[0]
        self.assertEqual(delete_fork_request.method, "DELETE")
        self.assertEqual(delete_fork_request.path, f"/repos/hmrc-read-only/{fork_name}")

    @httpretty.activate
    def test_delete_fork_that_does_not_exist(self) -> None:
        """
        Deleting a fork that does not exist should not make the script fail
        """
        fork_name = "some-fork-name"
        httpretty.register_uri(
            httpretty.DELETE,
            f"https://api.github.com/repos/hmrc-read-only/{fork_name}",
            status=204,
        )

        with patch("updater.fork_exists", return_value=False):
            with patch("updater.look_up_fork_name", return_value=fork_name):
                delete_fork()

        self.assertEqual(0, len(httpretty.latest_requests()))

    @httpretty.activate
    def test_delete_fork_not_allowed(self) -> None:
        """
        Fails to delete a fork because of permission denied
        """
        httpretty.register_uri(
            httpretty.DELETE,
            os.getenv("GIT_FORK_URL"),
            body=json.dumps(
                {
                    "message": "Must have admin rights to Repository.",
                    "documentation_url": "https://docs.github.com/rest/reference/repos#delete-a-repository",
                }
            ),
            status=403,
        )
        with patch("updater.fork_exists", return_value=True):
            with patch("updater.look_up_fork_name", return_value="some-fork-name"):
                with self.assertRaises(DeleteForkException):
                    delete_fork()

    def test_delete_fork_network_error(self) -> None:
        """
        Fails to delete a fork because of network error
        """
        with patch("updater.fork_exists", return_value=True):
            with patch("updater.look_up_fork_name", return_value="some-fork-name"):
                with patch("requests.delete", side_effect=RequestException):
                    with self.assertRaises(DeleteForkException):
                        delete_fork()


class TestRecreateFork(unittest.TestCase):
    def test_successfully_recreate_fork(self) -> None:
        with patch("updater.delete_fork", Mock()) as delete_fork_mock:
            with patch("updater.create_fork", Mock()) as create_fork_mock:
                with patch(
                    "updater.look_up_fork_name", Mock(return_value="build-dynamic-application-security-testing")
                ) as look_up_fork_name_mock:
                    mocks = Mock(
                        delete_fork=delete_fork_mock,
                        create_fork=create_fork_mock,
                        lookup_up_fork=look_up_fork_name_mock,
                    )
                    recreate_fork()

        mocks.assert_has_calls([call.delete_fork(), call.create_fork(), call.lookup_up_fork()])

    def test_recreate_fork_failure(self) -> None:
        with patch("updater.delete_fork", Mock()) as delete_fork_mock:
            with patch("updater.create_fork", Mock()) as create_fork_mock:
                with patch(
                    "updater.look_up_fork_name", Mock(return_value="build-dynamic-application-security-testing-1")
                ) as look_up_fork_name_mock:
                    with self.assertRaises(RecreateForkException):
                        mocks = Mock(
                            delete_fork=delete_fork_mock,
                            create_fork=create_fork_mock,
                            lookup_up_fork=look_up_fork_name_mock,
                        )
                        recreate_fork()

        self.assertEqual(45, len(mocks.mock_calls), "Expected 45 calls made of 15 retries of delete-create-lookup")
        mocks.assert_has_calls(
            [
                call.delete_fork(),
                call.create_fork(),
                call.lookup_up_fork(),
            ]
            * 15
        )


class TestCreateFork(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["GITHUB_API_TOKEN"] = "token 1234567890"

    @httpretty.activate
    def test_successfully_create_fork(self) -> None:
        """
        Successfully fork repository in GitHub
        """
        httpretty.register_uri(
            httpretty.POST,
            "https://api.github.com/repos/hmrc/build-dynamic-application-security-testing/forks",
            status=202,
        )
        with patch.dict(os.environ, {"GITHUB_API_USER": "some_username", "GITHUB_API_TOKEN": "some_token"}, clear=True):
            with patch("updater.fork_exists", return_value=True):
                create_fork()

        self.assertEqual(1, len(httpretty.latest_requests()))

        create_fork_request = httpretty.latest_requests()[0]
        self.assertEqual(create_fork_request.method, "POST")
        self.assertEqual(create_fork_request.path, "/repos/hmrc/build-dynamic-application-security-testing/forks")

    @httpretty.activate
    def test_fork_takes_too_long_to_create(self) -> None:
        """
        Makes a finite number of attempts at listing forks
        """
        httpretty.register_uri(
            httpretty.POST,
            os.getenv("GIT_API_FORK_URL"),
            status=202,
        )
        with patch("updater.fork_exists", return_value=False) as fork_exists_mock:
            with self.assertRaises(CreateForkException):
                create_fork()

        self.assertEqual(fork_exists_mock.call_count, 15, "Expected 15 retry calls to fork_exists method")

    @httpretty.activate
    def test_fork_creation_fails(self) -> None:
        """
        Failure when creating fork
        """
        httpretty.register_uri(
            httpretty.POST,
            os.getenv("GIT_API_FORK_URL"),
            status=500,
        )
        with self.assertRaises(CreateForkException):
            create_fork()


class TestGetFork(unittest.TestCase):
    @httpretty.activate
    def test_get_fork_success(self) -> None:
        fork_owner = "john"
        want_fork = {
            "name": "some-fork-name",
            "owner": {"login": fork_owner},
        }
        httpretty.register_uri(
            httpretty.GET,
            "https://api.github.com/repos/hmrc/build-dynamic-application-security-testing/forks",
            body=json.dumps(
                [
                    {
                        "name": "some-fork-name",
                        "owner": {"login": "some_other_fork_owner"},
                    },
                    want_fork,
                ]
            ),
            status=200,
        )
        with patch.dict(os.environ, {"GITHUB_API_USER": fork_owner, "GITHUB_API_TOKEN": "some_token"}, clear=True):
            got_fork = get_fork()

        self.assertEqual(got_fork, want_fork)

    @httpretty.activate
    def test_get_fork_not_found(self) -> None:
        fork_owner = "john"
        httpretty.register_uri(
            httpretty.GET,
            "https://api.github.com/repos/hmrc/build-dynamic-application-security-testing/forks",
            body=json.dumps(
                [
                    {
                        "name": "some-fork-name",
                        "owner": {"login": "some_other_fork_owner"},
                    }
                ]
            ),
            status=200,
        )
        with patch.dict(os.environ, {"GITHUB_API_USER": fork_owner, "GITHUB_API_TOKEN": "some_token"}, clear=True):
            with self.assertRaises(ForkNotFoundException):
                get_fork()


class TestForkExists(unittest.TestCase):
    @httpretty.activate
    def test_fork_does_exist(self) -> None:
        fork = {
            "name": "some-fork-name",
            "owner": {"login": "some-fork-owner"},
        }
        with patch("updater.get_fork", return_value=fork):
            self.assertTrue(fork_exists())

    @httpretty.activate
    def test_fork_does_not_exist(self) -> None:
        with patch("updater.get_fork", side_effect=ForkNotFoundException):
            self.assertFalse(fork_exists())


class TestCloneFork(unittest.TestCase):
    def test_successfully_clone_fork(self) -> None:
        """
        Successfully clone fork Git repository
        """
        want_fork_dir = os.path.join(os.getcwd(), "fork")
        want_fork_name = "some-fork-name"
        want_fork_url = f"https://some_username:some_token@github.com/hmrc-read-only/{want_fork_name}"
        want_args = ["git", "clone", want_fork_url, os.path.join(os.getcwd(), "fork")]

        mock_run = Mock(return_value=subprocess.CompletedProcess(args=want_args, returncode=0))

        with patch.dict(os.environ, {"GITHUB_API_USER": "some_username", "GITHUB_API_TOKEN": "some_token"}, clear=True):
            with patch("subprocess.run", mock_run):
                with patch("updater.look_up_fork_name", return_value=want_fork_name):
                    got_fork_dir = clone_fork()
        mock_run.assert_called_once_with(args=want_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        self.assertEqual(want_fork_dir, got_fork_dir)

    def test_can_not_clone_fork(self) -> None:
        """
        Clone fork Git repository fails
        """
        mock_run = Mock(
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=128,
                stdout="fatal: repository 'something' does not exist".encode("utf-8"),
            )
        )

        with patch.dict(os.environ, {"GITHUB_API_USER": "some_username", "GITHUB_API_TOKEN": "some_token"}, clear=True):
            with patch("subprocess.run", mock_run):
                with patch("updater.look_up_fork_name", return_value="some-fork-name"):
                    with self.assertRaises(CloneForkException):
                        clone_fork()


class TestCopyZapDockerfile(unittest.TestCase):
    def test_copy_zap_dockerfile_success(self) -> None:
        dockerfile_path = "/path/to/Dockerfile"
        fork_path = "/some/fork/path"
        with patch("os.chdir", Mock()) as mock_os:
            with patch("shutil.copyfile") as mock_copy:
                copy_zap_dockerfile_into_fork(dockerfile_path, fork_path)
        mock_os.assert_called_once_with(fork_path)
        mock_copy.assert_called_once_with(dockerfile_path, f"{fork_path}/Dockerfile")

    def test_copy_zap_dockerfile_failure(self) -> None:
        dockerfile_path = "/path/to/dockerfile"
        fork_path = "/some/fork/path"
        with patch("os.chdir", Mock()):
            with patch("shutil.copyfile", side_effect=shutil.Error):
                with self.assertRaises(CopyDockerfileToForkException):
                    copy_zap_dockerfile_into_fork(dockerfile_path, fork_path)


class TestGetenvOrRaise(unittest.TestCase):
    def setUpEnv(self) -> None:
        if self.token is None:
            return
        os.environ["TOKEN"] = self.token

    def test_get_correct_environment(self) -> None:
        """
        Validate environment variable TOKEN
        """
        self.token = "OTYwMDYwZGVlY2E2ZjRlMzJjYjYwYTllOTgwN"

        want_token = "OTYwMDYwZGVlY2E2ZjRlMzJjYjYwYTllOTgwN"

        self.setUpEnv()
        got_token = getenv_or_raise("TOKEN")

        self.assertEqual(got_token, want_token)

    def test_environment_with_whitepaces(self) -> None:
        """
        Use default value when env variable TOKEN is empty
        """
        self.token = "  \tOTYwMDYwZGVlY2E2ZjRlMzJjYjYwYTllOTgwN\n\r  "

        want_token = "OTYwMDYwZGVlY2E2ZjRlMzJjYjYwYTllOTgwN"

        self.setUpEnv()
        got_token = getenv_or_raise("TOKEN")

        self.assertEqual(got_token, want_token)

    def test_empty_environment(self) -> None:
        """
        Raise exception when env variable TOKEN is empty
        """
        self.token = ""

        self.setUpEnv()
        with self.assertRaises(GetEnvException):
            getenv_or_raise("TOKEN")

    def test_empty_environment_with_whitepaces(self) -> None:
        """
        Raise exception when env variable TOKEN is empty
        """
        self.token = "  \t\n\r  "

        self.setUpEnv()
        with self.assertRaises(GetEnvException):
            getenv_or_raise("TOKEN")

    def tearDown(self) -> None:
        os.environ.pop("TOKEN", None)


if __name__ == "__main__":
    unittest.main()
