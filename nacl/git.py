#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Handles git related stuff """
import sys
import os.path
import os
from subprocess import call
from subprocess import Popen, PIPE
from pprint import pprint
from nacl.helper import color, run, id_generator, merge_two_dicts
from nacl.fileutils import get_dir_list_from_filesystem
from nacl.fileutils import get_users_nacl_conf
import nacl.gitapi
from nacl.decorator import Log
import pprint


class GitCallError(Exception):
    pass


def list_git_repositories():
    """ using a list of local git repositories to check whether
        they have uncommitted changes or not and list them in a pretty way.
        TODO: This is not testable
    """

    git_repo_list = get_dir_list_from_filesystem('*.git')

    # Some Header
    # Fix this: Use a decorator for printing out stuff instead
    print("%-50s %-15s %-15s %-15s %s" % ("Directory", "Active Branch", "Status", "Local Master", "All Branches"))
    print("=" * 120)

    for git_repo in git_repo_list:
        check_git_repo(git_repo)


def merge_all_repositories():
    """ Merge all repositories at once when origin/master is ahead
        and the repository is clean.
        We will merge into local master!
        TODO: This is not testable
    """
    git_repo_list = get_dir_list_from_filesystem('*.git')
    for git_repo in git_repo_list:
        merge_git_repo(git_repo)


def merge_single_repository():
    """" Merges a single remote repo into the local branch. """
    merge_git_repo()


def merge_git_repo(git_repo_name=None):
    """ Do the heavy lifting of a merge """

    if git_repo_name:
        os.chdir(git_repo_name[:-4])

    branch = get_current_branch()
    dir_name = color('WARNING', run(['pwd']).rstrip())

    print(color("INFO", "Checking: ") + dir_name)

    # First check if there are any uncommitted changes.
    # In this case skip merging!
    if not branch_is_clean():
        print(color('INFO', 'Uncommitted changes, skipping...'))
        return True
    else:
        pass

    # We only merge into the local master branch
    if branch != 'master':
        print(color('FAIL', 'Checkout master'))
        checkout_branch('master')

    if need_pull_push(return_returncode=True) == 1:
        print(color("FAIL", "Need merge! ") + color("INFO", "Try to merge Branch: ") + color("GREEN", "master") + " in " + dir_name)
    else:
        # Switch back to prvevious branch
        if branch != 'master':
            print(color('INFO', 'Nothing to do in master... Switch back'))
            checkout_branch(branch)
        return True

    git(['fetch'])
    print(color("GREEN", "Start merge..."))
    git(['merge', '--ff-only', 'origin/master'])

    # Switch back to prvevious branch
    if branch != 'master':
        print(color('INFO', 'Switch back'))
        checkout_branch(branch)


@Log
def remote_diff():
    """ Shows the diffs between the local and the origin/master"""

    _ret = []

    if not branch_is_clean():
        _ret.append(('INFO', 'INFO: Uncommitted changes.'))

    git(['fetch'])
    output = git(['diff', 'master', 'origin/master'])
    if git(['diff', 'master', 'origin/master']):
        _ret.append(('INFO', output))
    else:
        _ret.append(('INFO', 'No diffs found'))

    return _ret


@Log
def checkout_branch(branch):

    print_is_git_repo()

    _ret = []

    if branch is None:
        git(['checkout', 'master'])
        _ret.append(('INFO', 'Branch: {0}'.format(get_current_branch())))
    elif branch == get_current_branch():
        _ret.append(('INFO', 'Already in {0}'.format(get_current_branch())))
    else:
        try:
            git(['checkout', branch])
            _ret.append(('INFO', 'Branch: {0}'.format(get_current_branch())))
        except GitCallError as exc:
            _ret.append(('FAIL', 'Unable to checkout {0} : {1}'.format(branch, exc)))

    return _ret


def is_git_repo(dir_name=None):
    """ Return whether it is a git repo or not """
    if dir_name is None:
        return os.path.exists('.git')
    else:
        return os.path.exists(dir_name + '.git')


@Log
def print_is_git_repo():
    """ Print and exit if is no repository """
    if not is_git_repo():
        return [('WARNING', 'No git repository found!', 1)]


def get_all_branches():
    """ Return a list with all branches """
    return git(['for-each-ref', '--format="%(refname:short)"', 'refs/heads/']).replace('"', '').split()


def branch_exist(branch):
    """ Check whether a branch already exists """
    exiting_branches = get_all_branches()
    for existing_branch in exiting_branches:
        if existing_branch == branch:
            return True
    return False


@Log
def change_or_create_branch(branch=None):
    """ Either creates (and switches into) a branch or just list branches """

    _ret = []

    print_is_git_repo()
    if branch is None:
        _ret.append(('INFO', git(['branch']).rstrip()))
    elif branch is not None and branch_exist(branch) is False:
        _ret.append(('INFO', 'Creating branch: {0}'.format(branch)))
        git(['branch', '--track', branch, 'origin/master'])
        git(['checkout', branch])
        _ret.append(('INFO', 'Switch into: {0}'.format(get_current_branch())))
    else:
        _ret.append(('INFO', "Branch exists. Change into {0}".format(branch)))
        git(['checkout', branch])

    return _ret


def remote_prune():
    """
    Removes staled remote refs (like old feature branches at the
    remote, that have been merged and deleted)
    """
    print git(['remote', 'prune', 'origin'])


def check_git_repo(git_repo_name=None):
    """ Checks the state of a single git repository """

    if git_repo_name is None:
        sys.stderr.write("No git repository provided!")
        sys.exit(3)

    os.chdir(git_repo_name[:-4])
    pretty_status()


def get_local_url_list():
    """ Get a list off all local repositories remote url's """
    url_list = []
    for repo in get_dir_list_from_filesystem('*.git'):
        os.chdir(repo[:-4])
        url_list.append(git(['config', '--get', 'remote.origin.url']).rstrip())

    return url_list


def compare_remote():
    """
    Compare the existence of remote and local git repositories and show
    missing local repositories.
    """
    local_repo_urls = get_local_url_list()

    print(color("FAIL", "WARNING: This list might be inaccurate!\n It will list remote git repositories, that are not in one of our salt environments!\n That might be ok!\n"))

    remote_url_dict = nacl.gitapi.get_remote_url_dict()

    for url, desc in remote_url_dict.iteritems():
        if url not in local_repo_urls:
                url = color("GREEN", url)
                desc = color("WARNING", desc)
                print("%-59s" % (url))
                print("%-59s\n" % (desc))


def git(args, env={}):
    """ @args: list
        @env: dict
        Some kind of git wrapping
    """

    user_config = get_users_nacl_conf()

    if env:
        env = env

    # We have to merge the os.environment and env, because we need HOME!
    env = merge_two_dicts(env, os.environ)

    # Any Proxy?
    try:
        proxy = user_config['proxy']
    except KeyError:
        proxy = False

    if proxy:
        env = merge_two_dicts(env, {'https_proxy': user_config['proxy']})

    p = Popen(['git'] + args, stdout=PIPE, stderr=PIPE, env=env)
    output, err = p.communicate()
    rc = p.wait()

    if err and rc != 0:
        raise GitCallError(err)
    return output


def branch_is_clean():
    """ Check whether a branch is clean """
    uncommited = git(['diff', '--name-only', 'HEAD'])
    if not uncommited:
        return True

    return False


def get_last_commit_sha():
    """ Return the current commit SHA"""
    return git(['rev-parse', 'HEAD'])


def is_commit_on_remote(sha=None, branch='master'):
    """ Check if sha is already in the remote branch"""
    if sha:
        try:
            remote_sha = git(['merge-base', sha.rstrip(), 'origin/' + branch])
            return bool(sha.rstrip() == remote_sha.rstrip())
        except:
            return False
    else:
        raise ValueError("sha must be provided")


def need_pull_push(return_returncode=False, local_branch='master', remote_branch='master'):
    """ Check whether we need to push or pull """
    git(['remote', 'update'])

    local = git(['rev-parse', local_branch])
    remote = git(['rev-parse', 'origin/' + remote_branch])
    base = git(['merge-base', local_branch, 'origin/' + remote_branch])

    # print "LOCAL: " + local
    # print "REMOTE: " + remote
    # print "BASE: " + base

    if local == remote:
        answer = color('INFO', "Up-to-date")
        code = 0
    elif local == base:
        answer = color('FAIL', "Need to pull")
        code = 1
    elif remote == base:
        answer = color('HEADER', "Need to push")
        code = 2
    else:
        answer = "Diverged"
        code = 3

    if return_returncode is True:
        return code

    return answer


def get_current_branch():
    """ Returns the current active branch """
    branch = git(['rev-parse', '--abbrev-ref', 'HEAD'])
    return branch.rstrip()


def is_merged(branch):
    """ Check whether a local branch is already merged into origin/master """
    git(['remote', 'update'])
    local = git(['rev-parse', '@']).rstrip()
    remote = git(['merge-base', local, 'origin/master']).rstrip()
    if local == remote:
        return True
    else:
        return False


def print_merge_status(branch):
    """ Print out the merge status of branch """
    if is_merged(branch):
        return color('INFO', "(merged)")
    else:
        return color('FAIL', "(unmerged)")


def pretty_status():
    """ Prints out some information about a repository """
    branch = get_current_branch()
    status = git(['status', '-s']).rstrip()
    pull_push = need_pull_push()
    merge_status = ''
    all_branches = color('DARKCYAN', ', '.join(get_all_branches()))

    if branch_is_clean():
        status = color('UNDERLINE', "Clean")
    else:
        status = color('FAIL', status[0:10])

    if branch != 'master':
        merge_status = print_merge_status(branch)
        branch = color('GREEN', branch)

    dir_name = color('WARNING', run(['pwd']).rstrip())

    print("%-59s %-13s %1s %-23s %-24s %s" % (dir_name, branch, merge_status, status, pull_push, all_branches))
    pass


def initial_clone(repository=None, destination=None, proxy=None):

    if repository is None or destination is None:
        sys.stderr.write("Die Angaben zum Git Repo oder zum Zielort des git clone dürfen nicht leer sein!")
        sys.exit(1)

    # es wird in ein temp Verzeichnis geclont, weil i.d.R. das eigentliche
    # Zielverzeichnis schon vorhanden ist und ein `git clone` mit einem Fehler abbrechen
    # würde.

    tmp_dir = "/tmp/" + id_generator()

    # Fürs Clonen aus dem Internet müssen wir eine Umgebungsvariable setzen,
    # nämlich `https_proxy`
    if proxy is not None:
        env = {'https_proxy': proxy}
    else:
        env = {}
    # Clonen
    pprint(git(['clone', repository, tmp_dir], env=env))

    # Dateien an den eigentlichen Ort bringen.
    # rsync hat im Zusammenhang mit Python hier am Besten funktioniert.
    call(["rsync", "-a", tmp_dir + "/", destination])

    # Aufräumen
    pprint(call(['rm', '-rf', tmp_dir]))
